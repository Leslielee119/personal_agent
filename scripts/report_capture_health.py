from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_predictive_ai.diagnostics.health import build_health_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a local capture health report.")
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--samples", type=Path, default=None)
    parser.add_argument("--runtime-status", type=Path, default=None)
    parser.add_argument("--forbid-string", action="append", default=[])
    parser.add_argument("--raw-ttl-seconds", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = build_health_report(
        args.data_dir,
        samples_path=args.samples,
        runtime_status_path=args.runtime_status,
        forbidden_strings=tuple(args.forbid_string),
        raw_ttl_seconds=args.raw_ttl_seconds,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
