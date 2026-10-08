from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from personal_predictive_ai.continuity.models import GitWorkCopyState, WorkCopyRecord


class GitObserver:
    def observe(self, workcopy: WorkCopyRecord, *, now_ns: int) -> GitWorkCopyState:
        root = Path(workcopy.canonical_root).resolve(strict=True)
        head = self._run(root, "rev-parse", "HEAD").decode("utf-8").strip()
        branch = self._run(root, "rev-parse", "--abbrev-ref", "HEAD").decode("utf-8").strip()
        status = self._run(
            root,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
        )
        tracked_diff = self._run(
            root,
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--binary",
            "HEAD",
            "--",
        )
        tracked_digest = hashlib.sha256(tracked_diff).hexdigest()
        untracked_digest = self._untracked_digest(root, status)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "head_commit": head,
                    "tracked_diff_digest": tracked_digest,
                    "untracked_digest": untracked_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return GitWorkCopyState(
            workcopy_id=workcopy.workcopy_id,
            head_commit=head,
            branch_hint=branch or "HEAD",
            is_dirty=bool(status),
            tracked_diff_digest=tracked_digest,
            untracked_digest=untracked_digest,
            code_state_fingerprint=fingerprint,
            observed_at_ns=now_ns,
        )

    @staticmethod
    def _run(root: Path, *args: str) -> bytes:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
        )
        return bytes(completed.stdout)

    @staticmethod
    def _untracked_digest(root: Path, status: bytes) -> str:
        entries: list[tuple[str, bytes]] = []
        for raw in status.split(b"\x00"):
            if not raw.startswith(b"?? "):
                continue
            relative = os.fsdecode(raw[3:])
            candidate = (root / relative).resolve(strict=True)
            if not candidate.is_relative_to(root):
                raise ValueError("untracked path escapes registered workcopy")
            if not candidate.is_file():
                continue
            entries.append((relative.replace("\\", "/"), candidate.read_bytes()))
        digest = hashlib.sha256()
        for relative, content in sorted(entries):
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(b"\x00")
            digest.update(content)
            digest.update(b"\x00")
        return digest.hexdigest()
