from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from personal_predictive_ai.collector.base import Collector, CollectorContext
from personal_predictive_ai.config import Settings
from personal_predictive_ai.continuity.brief import ResumeBriefService
from personal_predictive_ai.continuity.corrections import CorrectionService, EvidenceViewService
from personal_predictive_ai.continuity.registry import ContinuityRegistry
from personal_predictive_ai.continuity.state import TaskStateService
from personal_predictive_ai.diagnostics.memory_replay import derive_b2, iter_b2_replay_lines
from personal_predictive_ai.diagnostics.state_replay import derive_b1, iter_b1_replay_lines
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.knowledge.models import KnowledgeRecord
from personal_predictive_ai.prediction.benchmark import run_milestone_c
from personal_predictive_ai.prediction.longitudinal import run_longitudinal_cycle
from personal_predictive_ai.prediction.readiness import audit_longitudinal_status
from personal_predictive_ai.runtime.service import CaptureService, ServiceStatus
from personal_predictive_ai.skills.models import SkillDraft, SkillStatus
from personal_predictive_ai.skills.packages import (
    PackageScanBlockedError,
    PackageTamperedError,
    UnsafePackagePathError,
    approve_package,
    quarantine_local_package,
    scan_package,
)
from personal_predictive_ai.skills.projection import projection_manifest_for, render_skill_markdown
from personal_predictive_ai.skills.registry import (
    RiskDowngradeApprovalRequired,
    StaleSkillVersionError,
    TrustedRegistryService,
    UnsupportedE1TransitionError,
    UntrustedSkillPackageError,
)
from personal_predictive_ai.skills.retrieval import get_skill_core, list_skill_index
from personal_predictive_ai.storage.continuity_store import ContinuityStore
from personal_predictive_ai.storage.derived_store import DerivedStore
from personal_predictive_ai.storage.knowledge_skill_store import KnowledgeSkillStore
from personal_predictive_ai.storage.memory_store import MemoryStore


def _settings_from_args(args: argparse.Namespace) -> Settings:
    values: dict[str, object] = {}
    if args.data_dir is not None:
        values["data_dir"] = Path(args.data_dir)
    if args.raw_ttl_seconds is not None:
        values["raw_ttl_seconds"] = args.raw_ttl_seconds
    return Settings(**values)


def _status_payload(status: ServiceStatus, *, offline_mode: bool) -> dict[str, object]:
    payload = asdict(status)
    payload["offline_mode"] = offline_mode
    return payload


def _collector_factory(
    *,
    use_openadapt: bool,
    watch_roots: tuple[Path, ...] = (),
):
    def build(context: CollectorContext) -> list[Collector]:
        from personal_predictive_ai.collector.process import ProcessCollector
        from personal_predictive_ai.collector.windows_foreground import (
            ForegroundWindowCollector,
        )
        from personal_predictive_ai.collector.windows_notifications import (
            WindowsNotificationCollector,
        )

        factory = context.event_factory
        collectors: list[Collector] = [
            ProcessCollector(factory=factory),
            ForegroundWindowCollector(factory=factory),
            WindowsNotificationCollector(factory=factory),
        ]
        if watch_roots:
            from personal_predictive_ai.collector.filesystem import FilesystemCollector

            excluded_paths: list[Path] = [context.raw_ring.root.parent]
            for root in watch_roots:
                excluded_paths.extend(
                    root / name
                    for name in (
                        ".git",
                        ".venv",
                        ".pytest_cache",
                        "node_modules",
                        "__pycache__",
                    )
                )
            collectors.append(
                FilesystemCollector(
                    factory=factory,
                    roots=watch_roots,
                    excluded_paths=excluded_paths,
                )
            )
        if use_openadapt:
            from personal_predictive_ai.collector.openadapt import OpenAdaptCollector
            from personal_predictive_ai.collector.screen import ScreenSnapshotter

            snapshotter = ScreenSnapshotter(factory=factory, raw_ring=context.raw_ring)
            collectors.append(
                OpenAdaptCollector(
                    factory=factory,
                    capture_structural=True,
                    snapshotter=snapshotter,
                )
            )
        return collectors

    return build


def _add_capture_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--stop-file", type=Path, default=None)
    parser.add_argument("--watch-root", type=Path, action="append", default=[])
    parser.add_argument(
        "--openadapt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable native keyboard/mouse/UIA plus event-driven screen capture",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ppa")
    parser.add_argument("--data-dir")
    parser.add_argument("--raw-ttl-seconds", type=int)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    _add_capture_args(capture)

    derive = subparsers.add_parser("derive-b1")
    derive.add_argument("--run-id", required=True)
    replay = subparsers.add_parser("replay-b1")
    replay.add_argument("--run-id", required=True)
    replay.add_argument("--limit", type=int, default=None)

    derive_b2_parser = subparsers.add_parser("derive-b2")
    derive_b2_parser.add_argument("--source-b1-run-id", required=True)
    derive_b2_parser.add_argument("--run-id", required=True)
    replay_b2_parser = subparsers.add_parser("replay-b2")
    replay_b2_parser.add_argument("--run-id", required=True)
    replay_b2_parser.add_argument("--limit", type=int, default=None)

    benchmark_c_parser = subparsers.add_parser("benchmark-c")
    benchmark_c_parser.add_argument("--source-b1-run-id", required=True)
    benchmark_c_parser.add_argument("--source-b2-run-id", default=None)
    benchmark_c_parser.add_argument("--run-id", required=True)

    longitudinal_parser = subparsers.add_parser("longitudinal-status")
    longitudinal_parser.add_argument("--source-b1-run-id", required=True)

    longitudinal_cycle = subparsers.add_parser("longitudinal-cycle")
    longitudinal_cycle.add_argument("--run-id", default="longitudinal-current")

    longitudinal_session = subparsers.add_parser("longitudinal-session")
    _add_capture_args(longitudinal_session)
    longitudinal_session.add_argument("--run-id", default="longitudinal-current")

    continuity_init = subparsers.add_parser("continuity-init")
    continuity_init.add_argument("--project-key", required=True)
    continuity_init.add_argument("--workcopy-root", type=Path, required=True)
    continuity_init.add_argument("--task-title", required=True)
    continuity_init.add_argument("--goal", default="")
    continuity_init.add_argument("--last-position", default="")
    continuity_init.add_argument("--next-step", default="")

    continuity_resume = subparsers.add_parser("continuity-resume")
    continuity_resume.add_argument("--task-id", required=True)
    continuity_resume.add_argument("--format", choices=["text", "json"], default="text")

    continuity_correct = subparsers.add_parser("continuity-correct")
    continuity_correct.add_argument("--task-id", required=True)
    continuity_correct.add_argument("--field", required=True)
    continuity_correct.add_argument("--value", required=True)
    continuity_correct.add_argument("--action", choices=["set", "add", "resolve"], default="set")

    continuity_evidence = subparsers.add_parser("continuity-evidence")
    continuity_evidence.add_argument("--task-id", required=True)
    continuity_evidence.add_argument("--field", default=None)

    continuity_forget = subparsers.add_parser("continuity-forget")
    continuity_forget.add_argument(
        "--scope", choices=["evidence", "task", "workcopy", "project"], required=True
    )
    continuity_forget.add_argument("--id", required=True)

    knowledge_import = subparsers.add_parser("knowledge-import")
    knowledge_import.add_argument("--file", type=Path, required=True)

    skill_stage = subparsers.add_parser("skill-stage")
    skill_stage.add_argument("--file", type=Path, required=True)
    skill_stage.add_argument("--proposed-by", required=True)
    skill_stage.add_argument("--package-id", default=None)

    skill_approve = subparsers.add_parser("skill-approve")
    skill_approve.add_argument("--proposal-id", required=True)
    skill_approve.add_argument("--approver", required=True)
    skill_approve.add_argument("--allow-risk-downgrade", action="store_true")

    skill_list = subparsers.add_parser("skill-list")
    skill_list.add_argument("--status", choices=[item.value for item in SkillStatus])

    skill_show = subparsers.add_parser("skill-show")
    skill_show.add_argument("--skill-id", required=True)
    skill_show.add_argument("--level", choices=["index", "core"], required=True)
    skill_show.add_argument("--version", type=int, default=None)

    skill_export = subparsers.add_parser("skill-export")
    skill_export.add_argument("--skill-id", required=True)
    skill_export.add_argument("--output", type=Path, required=True)
    skill_export.add_argument("--version", type=int, default=None)

    package_import = subparsers.add_parser("skill-package-import")
    package_import.add_argument("--path", type=Path, required=True)
    package_import.add_argument("--source-uri", required=True)
    package_import.add_argument("--source-revision", required=True)

    package_scan = subparsers.add_parser("skill-package-scan")
    package_scan.add_argument("--package-id", required=True)

    package_approve = subparsers.add_parser("skill-package-approve")
    package_approve.add_argument("--package-id", required=True)
    package_approve.add_argument("--reviewer", required=True)

    subparsers.add_parser("status")
    expire = subparsers.add_parser("expire-raw")
    expire.add_argument("--now-ns", type=int, default=None)
    return parser


_E1_COMMANDS = {
    "knowledge-import",
    "skill-stage",
    "skill-approve",
    "skill-list",
    "skill-show",
    "skill-export",
    "skill-package-import",
    "skill-package-scan",
    "skill-package-approve",
}

_CONTINUITY_COMMANDS = {
    "continuity-init",
    "continuity-resume",
    "continuity-correct",
    "continuity-evidence",
    "continuity-forget",
}


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _error_code(exc: Exception) -> str:
    mapping = {
        UntrustedSkillPackageError: "untrusted_skill_package",
        PackageScanBlockedError: "package_scan_blocked",
        PackageTamperedError: "package_tampered",
        UnsafePackagePathError: "unsafe_package_path",
        RiskDowngradeApprovalRequired: "risk_downgrade_requires_approval",
        StaleSkillVersionError: "stale_skill_version",
        UnsupportedE1TransitionError: "unsupported_e1_transition",
    }
    for error_type, code in mapping.items():
        if isinstance(exc, error_type):
            return code
    return "validation_error"


def _run_e1_command(args: argparse.Namespace, settings: Settings) -> int:
    store = KnowledgeSkillStore(settings.data_dir / "events.db")
    service = TrustedRegistryService(store)
    quarantine_root = settings.data_dir / "skill-packages" / "quarantine"
    try:
        if args.command == "knowledge-import":
            record = KnowledgeRecord.model_validate_json(args.file.read_text(encoding="utf-8"))
            _print_json(service.import_human_knowledge(record).model_dump(mode="json"))
        elif args.command == "skill-stage":
            draft = SkillDraft.model_validate_json(args.file.read_text(encoding="utf-8"))
            if args.package_id is not None:
                draft = draft.model_copy(update={"source_package_id": args.package_id})
            proposal = service.stage_skill_create(draft, proposed_by=args.proposed_by)
            _print_json(proposal.model_dump(mode="json"))
        elif args.command == "skill-approve":
            record = service.approve_proposal(
                args.proposal_id,
                approver=args.approver,
                allow_risk_downgrade=args.allow_risk_downgrade,
            )
            _print_json(record.model_dump(mode="json"))
        elif args.command == "skill-list":
            statuses = None if args.status is None else {SkillStatus(args.status)}
            items = list_skill_index(store, statuses=statuses)
            _print_json([item.model_dump(mode="json") for item in items])
        elif args.command == "skill-show":
            record = store.get_skill(args.skill_id, args.version)
            if record is None:
                raise KeyError(args.skill_id)
            if args.level == "core":
                payload = get_skill_core(
                    store,
                    args.skill_id,
                    version=args.version,
                ).model_dump(mode="json")
            else:
                payload = {
                    "skill_id": record.skill_id,
                    "name": record.name,
                    "purpose": record.purpose,
                    "kind": record.kind.value,
                    "risk_class": record.risk_class.value,
                    "status": record.status.value,
                    "version": record.version,
                }
            _print_json(payload)
        elif args.command == "skill-export":
            record = store.get_skill(args.skill_id, args.version)
            if record is None:
                raise KeyError(args.skill_id)
            content = render_skill_markdown(record)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
            manifest = projection_manifest_for(record, output_path=args.output, content=content)
            store.put_projection_manifest(manifest)
            _print_json(manifest.model_dump(mode="json"))
        elif args.command == "skill-package-import":
            manifest = quarantine_local_package(
                store,
                args.path,
                source_uri=args.source_uri,
                source_revision=args.source_revision,
                quarantine_root=quarantine_root,
            )
            _print_json(manifest.model_dump(mode="json"))
        elif args.command == "skill-package-scan":
            manifest = scan_package(store, args.package_id, quarantine_root=quarantine_root)
            _print_json(manifest.model_dump(mode="json"))
        elif args.command == "skill-package-approve":
            manifest = approve_package(
                store,
                args.package_id,
                reviewer=args.reviewer,
                quarantine_root=quarantine_root,
            )
            _print_json(manifest.model_dump(mode="json"))
        else:
            raise ValueError(f"unsupported E1 command: {args.command}")
        return 0
    except (
        ValueError,
        KeyError,
        OSError,
        UntrustedSkillPackageError,
        PackageScanBlockedError,
        PackageTamperedError,
        UnsafePackagePathError,
        RiskDowngradeApprovalRequired,
        StaleSkillVersionError,
        UnsupportedE1TransitionError,
    ) as exc:
        _print_json({"error": _error_code(exc), "detail": str(exc)})
        return 2
    finally:
        store.close()


def _run_continuity_command(args: argparse.Namespace, settings: Settings) -> int:
    store = ContinuityStore(settings.data_dir / "continuity.db")
    registry = ContinuityRegistry(store)
    state = TaskStateService(store)
    brief_service = ResumeBriefService(store)
    try:
        now_ns = time.time_ns()
        if args.command == "continuity-init":
            binding = registry.bind(
                args.project_key,
                args.workcopy_root,
                args.task_title,
                now_ns=now_ns,
            )
            snapshot = state.initialize(
                binding.task.task_id,
                current_goal=args.goal,
                last_position=args.last_position,
                next_step=args.next_step,
                now_ns=now_ns,
            )
            _print_json(
                {
                    "project_id": binding.project.project_id,
                    "workcopy_id": binding.workcopy.workcopy_id,
                    "task_id": binding.task.task_id,
                    "snapshot_id": snapshot.snapshot_id,
                }
            )
        elif args.command == "continuity-resume":
            snapshot = state.build(args.task_id, as_of_ns=now_ns)
            brief = brief_service.render(snapshot, generated_at_ns=now_ns)
            if args.format == "json":
                _print_json(
                    {
                        "snapshot": snapshot.model_dump(mode="json"),
                        "brief": brief.model_dump(mode="json"),
                    }
                )
            else:
                print(brief_service.render_text(brief))
        elif args.command == "continuity-correct":
            corrections = CorrectionService(store)
            if args.action == "set":
                snapshot = corrections.correct_scalar(
                    args.task_id, args.field, args.value, now_ns=now_ns
                )
            elif args.action == "add":
                snapshot = corrections.add_item(
                    args.task_id, args.field, args.value, now_ns=now_ns
                )
            else:
                snapshot = corrections.resolve_item(
                    args.task_id, args.field, args.value, now_ns=now_ns
                )
            _print_json({"snapshot": snapshot.model_dump(mode="json")})
        elif args.command == "continuity-evidence":
            items = EvidenceViewService(store).list_for_task(
                args.task_id, field_name=args.field
            )
            _print_json([item.model_dump(mode="json") for item in items])
        elif args.command == "continuity-forget":
            tombstone = CorrectionService(store).forget(
                args.scope, args.id, now_ns=now_ns
            )
            _print_json(tombstone.model_dump(mode="json"))
        else:
            raise ValueError(f"unsupported continuity command: {args.command}")
        return 0
    except (KeyError, OSError, ValueError) as exc:
        _print_json({"error": "continuity_error", "detail": str(exc)})
        return 2
    finally:
        store.close()


def _run_capture(
    args: argparse.Namespace,
    settings: Settings,
    factory: EventFactory,
) -> dict[str, object]:
    watch_roots = tuple(Path(path).resolve() for path in args.watch_root)
    service = CaptureService(
        settings=settings,
        collectors=[],
        event_factory=factory,
        collector_factory=_collector_factory(
            use_openadapt=args.openadapt,
            watch_roots=watch_roots,
        ),
    )
    try:
        service.start()
        now = time.monotonic()
        deadline = None if args.duration is None else now + max(0.0, args.duration)
        maintenance_period = max(1.0, min(30.0, settings.raw_ttl_seconds / 4.0))
        next_raw_maintenance = now + maintenance_period
        structured_maintenance_period = 300.0
        next_structured_maintenance = now + structured_maintenance_period
        while deadline is None or time.monotonic() < deadline:
            if args.stop_file is not None and args.stop_file.exists():
                break
            now = time.monotonic()
            if now >= next_raw_maintenance:
                service.expire_raw()
                next_raw_maintenance = now + maintenance_period
            if now >= next_structured_maintenance:
                service.expire_structured_short()
                next_structured_maintenance = now + structured_maintenance_period
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        service.expire_raw()
        service.expire_structured_short()
        service.stop()
        payload = _status_payload(service.status(), offline_mode=settings.offline_mode)
        service.close()
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _settings_from_args(args)
    factory = EventFactory()

    if args.command in _E1_COMMANDS:
        return _run_e1_command(args, settings)
    if args.command in _CONTINUITY_COMMANDS:
        return _run_continuity_command(args, settings)

    if args.command == "derive-b1":
        summary = derive_b1(settings.data_dir / "events.db", run_id=args.run_id)
        print(json.dumps(summary, sort_keys=True))
        return 0

    if args.command == "replay-b1":
        store = DerivedStore(settings.data_dir / "events.db")
        try:
            for line in iter_b1_replay_lines(store, args.run_id, limit=args.limit):
                print(line)
        finally:
            store.close()
        return 0

    if args.command == "derive-b2":
        summary = derive_b2(
            settings.data_dir / "events.db",
            source_b1_run_id=args.source_b1_run_id,
            run_id=args.run_id,
        )
        print(json.dumps(summary, sort_keys=True))
        return 0

    if args.command == "replay-b2":
        store = MemoryStore(settings.data_dir / "events.db")
        try:
            for line in iter_b2_replay_lines(store, args.run_id, limit=args.limit):
                print(line)
        finally:
            store.close()
        return 0

    if args.command == "benchmark-c":
        summary = run_milestone_c(
            settings.data_dir / "events.db",
            source_b1_run_id=args.source_b1_run_id,
            source_b2_run_id=args.source_b2_run_id,
            run_id=args.run_id,
            output_root=settings.data_dir,
        )
        print(json.dumps(summary.model_dump(mode="json"), sort_keys=True))
        return 0

    if args.command == "longitudinal-status":
        report = audit_longitudinal_status(
            settings.data_dir / "events.db",
            source_b1_run_id=args.source_b1_run_id,
        )
        print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
        return 0

    if args.command == "longitudinal-cycle":
        report = run_longitudinal_cycle(
            settings.data_dir / "events.db",
            run_id=args.run_id,
        )
        print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
        return 0

    if args.command == "capture":
        payload = _run_capture(args, settings, factory)
        print(json.dumps(payload, sort_keys=True))
        return 0

    if args.command == "longitudinal-session":
        capture_payload = _run_capture(args, settings, factory)
        report = run_longitudinal_cycle(
            settings.data_dir / "events.db",
            run_id=args.run_id,
        )
        print(
            json.dumps(
                {
                    "capture": capture_payload,
                    "longitudinal": report.model_dump(mode="json"),
                },
                sort_keys=True,
            )
        )
        return 0

    if args.command == "status":
        service = CaptureService(settings=settings, collectors=[], event_factory=factory)
        try:
            print(json.dumps(_status_payload(service.status(), offline_mode=settings.offline_mode)))
        finally:
            service.close()
        return 0

    if args.command == "expire-raw":
        service = CaptureService(settings=settings, collectors=[], event_factory=factory)
        try:
            expired = service.expire_raw(now_ns=args.now_ns)
            print(json.dumps({"expired": expired, "offline_mode": settings.offline_mode}))
        finally:
            service.close()
        return 0

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
