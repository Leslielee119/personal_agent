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
        reported_root = self._run(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
        resolved_reported_root = Path(reported_root).resolve(strict=True)
        if os.path.normcase(str(resolved_reported_root)) != os.path.normcase(str(root)):
            raise ValueError("git repository root does not match registered workcopy root")
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
        env = os.environ.copy()
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "core.fsmonitor"
        env["GIT_CONFIG_VALUE_0"] = "false"
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            env=env,
        )
        return bytes(completed.stdout)

    @staticmethod
    def _untracked_digest(root: Path, status: bytes) -> str:
        entries: list[tuple[str, str]] = []
        for raw in status.split(b"\x00"):
            if not raw.startswith(b"?? "):
                continue
            relative = os.fsdecode(raw[3:])
            candidate = (root / relative).resolve(strict=True)
            if not candidate.is_relative_to(root):
                raise ValueError("untracked path escapes registered workcopy")
            if not candidate.is_file():
                continue
            entries.append((relative.replace("\\", "/"), _stream_sha256(candidate)))
        digest = hashlib.sha256()
        for relative, content_digest in sorted(entries):
            digest.update(relative.encode("utf-8", errors="surrogateescape"))
            digest.update(b"\x00")
            digest.update(content_digest.encode("ascii"))
            digest.update(b"\x00")
        return digest.hexdigest()


def _stream_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
