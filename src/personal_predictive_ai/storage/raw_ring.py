from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable
from pathlib import Path


class RawRing:
    def __init__(
        self,
        root: str | Path,
        *,
        ttl_seconds: int,
        max_bytes: int,
        clock_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_ns = ttl_seconds * 1_000_000_000
        self.max_bytes = max_bytes
        self._clock_ns = clock_ns

    def put(self, data: bytes, suffix: str = "") -> str:
        suffix = self._safe_suffix(suffix)
        created_ns = self._clock_ns()
        ref = f"{created_ns:020d}-{uuid.uuid4().hex}{suffix}"
        final_path = self.root / ref
        meta_path = self._meta_path(ref)

        with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temp_data = Path(handle.name)

        meta = {"ref": ref, "created_ns": created_ns, "size": len(data)}
        with tempfile.NamedTemporaryFile(
            dir=self.root,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as handle:
            json.dump(meta, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
            temp_meta = Path(handle.name)

        os.replace(temp_data, final_path)
        os.replace(temp_meta, meta_path)
        self._enforce_size()
        return ref

    def resolve(self, raw_ref: str) -> Path | None:
        if not raw_ref or Path(raw_ref).name != raw_ref:
            return None
        candidate = self.root / raw_ref
        try:
            if candidate.resolve().parent != self.root.resolve():
                return None
        except OSError:
            return None
        return candidate if candidate.is_file() else None

    def expire(self, now_ns: int | None = None) -> int:
        now_ns = self._clock_ns() if now_ns is None else now_ns
        expired = 0
        for entry in self._entries():
            if entry["created_ns"] + self.ttl_ns <= now_ns:
                self._delete(entry["ref"])
                expired += 1
        return expired

    def total_bytes(self) -> int:
        total = 0
        for entry in self._entries():
            path = self.resolve(entry["ref"])
            if path is not None:
                total += path.stat().st_size
        return total

    def _enforce_size(self) -> None:
        entries = sorted(self._entries(), key=lambda item: (item["created_ns"], item["ref"]))
        total = sum(
            path.stat().st_size
            for entry in entries
            if (path := self.resolve(entry["ref"])) is not None
        )
        for entry in entries:
            if total <= self.max_bytes:
                break
            path = self.resolve(entry["ref"])
            size = path.stat().st_size if path is not None else 0
            self._delete(entry["ref"])
            total -= size

    def _entries(self) -> list[dict[str, int | str]]:
        entries: list[dict[str, int | str]] = []
        for meta_path in self.root.glob("*.meta.json"):
            try:
                item = json.loads(meta_path.read_text(encoding="utf-8"))
                ref = str(item["ref"])
                created_ns = int(item["created_ns"])
                size = int(item["size"])
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
                continue
            entries.append({"ref": ref, "created_ns": created_ns, "size": size})
        return entries

    def _delete(self, ref: str) -> None:
        path = self.resolve(ref)
        if path is not None:
            path.unlink(missing_ok=True)
        self._meta_path(ref).unlink(missing_ok=True)

    def _meta_path(self, ref: str) -> Path:
        return self.root / f"{ref}.meta.json"

    @staticmethod
    def _safe_suffix(suffix: str) -> str:
        if not suffix:
            return ""
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if any(not (char.isalnum() or char in {".", "_", "-"}) for char in suffix):
            raise ValueError("unsafe artifact suffix")
        if "/" in suffix or "\\" in suffix:
            raise ValueError("unsafe artifact suffix")
        return suffix
