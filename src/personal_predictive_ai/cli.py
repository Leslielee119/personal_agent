from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from personal_predictive_ai.collector.base import Collector, CollectorContext
from personal_predictive_ai.config import Settings
from personal_predictive_ai.diagnostics.memory_replay import derive_b2, iter_b2_replay_lines
from personal_predictive_ai.diagnostics.state_replay import derive_b1, iter_b1_replay_lines
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.prediction.benchmark import run_milestone_c
from personal_predictive_ai.prediction.readiness import audit_longitudinal_status
from personal_predictive_ai.runtime.service import CaptureService, ServiceStatus
from personal_predictive_ai.storage.derived_store import DerivedStore
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ppa")
    parser.add_argument("--data-dir")
    parser.add_argument("--raw-ttl-seconds", type=int)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--duration", type=float, default=None)
    capture.add_argument("--stop-file", type=Path, default=None)
    capture.add_argument("--watch-root", type=Path, action="append", default=[])
    capture.add_argument(
        "--openadapt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable native keyboard/mouse/UIA plus event-driven screen capture",
    )

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

    subparsers.add_parser("status")
    expire = subparsers.add_parser("expire-raw")
    expire.add_argument("--now-ns", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _settings_from_args(args)
    factory = EventFactory()

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
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
