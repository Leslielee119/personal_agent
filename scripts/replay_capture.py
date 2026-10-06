from __future__ import annotations

import argparse
from pathlib import Path

from personal_predictive_ai.diagnostics.replay import iter_replay_lines
from personal_predictive_ai.storage.raw_ring import RawRing
from personal_predictive_ai.storage.sqlite_store import EventStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a safe chronological capture trace.")
    parser.add_argument("data_dir", type=Path)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    store = EventStore(args.data_dir / "events.db")
    ring = RawRing(args.data_dir / "raw", ttl_seconds=1, max_bytes=1)
    try:
        for line in iter_replay_lines(store, raw_ring=ring, limit=args.limit):
            print(line)
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
