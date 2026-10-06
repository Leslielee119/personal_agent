from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from personal_predictive_ai.collector.base import Collector
from personal_predictive_ai.config import Settings
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.runtime.service import CaptureService, ServiceStatus


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


def _collector_factory(*, use_openadapt: bool):
    def build(factory: EventFactory) -> list[Collector]:
        from personal_predictive_ai.collector.process import ProcessCollector

        collectors: list[Collector] = [ProcessCollector(factory=factory)]
        if use_openadapt:
            from personal_predictive_ai.collector.openadapt import OpenAdaptCollector

            collectors.append(OpenAdaptCollector(factory=factory, capture_structural=True))
        return collectors

    return build


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ppa")
    parser.add_argument("--data-dir")
    parser.add_argument("--raw-ttl-seconds", type=int)
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser("capture")
    capture.add_argument("--duration", type=float, default=None)
    capture.add_argument(
        "--openadapt",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable native keyboard/mouse/UIA capture",
    )

    subparsers.add_parser("status")
    expire = subparsers.add_parser("expire-raw")
    expire.add_argument("--now-ns", type=int, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = _settings_from_args(args)
    factory = EventFactory()

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

    service = CaptureService(
        settings=settings,
        collectors=[],
        event_factory=factory,
        collector_factory=_collector_factory(use_openadapt=args.openadapt),
    )
    try:
        service.start()
        deadline = None if args.duration is None else time.monotonic() + max(0.0, args.duration)
        while deadline is None or time.monotonic() < deadline:
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        payload = _status_payload(service.status(), offline_mode=settings.offline_mode)
        service.close()
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
