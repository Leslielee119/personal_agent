from __future__ import annotations

import subprocess
from pathlib import Path

from personal_predictive_ai.continuity.git_observer import GitObserver
from personal_predictive_ai.continuity.models import WorkCopyRecord


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> tuple[Path, WorkCopyRecord]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-m", "initial")
    record = WorkCopyRecord(
        workcopy_id="workcopy:1",
        project_id="project:1",
        canonical_root=str(root.resolve()),
        created_at_ns=1,
        last_seen_at_ns=1,
    )
    return root, record


def test_git_observer_fingerprint_changes_for_tracked_and_untracked_content(tmp_path: Path) -> None:
    root, workcopy = _repo(tmp_path)
    observer = GitObserver()
    clean = observer.observe(workcopy, now_ns=10)
    assert clean.is_dirty is False

    (root / "a.txt").write_text("two\n", encoding="utf-8")
    tracked = observer.observe(workcopy, now_ns=20)
    assert tracked.is_dirty is True
    assert tracked.code_state_fingerprint != clean.code_state_fingerprint

    (root / "b.txt").write_text("untracked\n", encoding="utf-8")
    untracked = observer.observe(workcopy, now_ns=30)
    assert untracked.untracked_digest != tracked.untracked_digest
    assert untracked.code_state_fingerprint != tracked.code_state_fingerprint


def test_git_observer_uses_only_fixed_read_only_git_argv(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    workcopy = WorkCopyRecord(
        workcopy_id="workcopy:1", project_id="project:1", canonical_root=str(root),
        created_at_ns=1, last_seen_at_ns=1,
    )
    calls: list[tuple[str, ...]] = []

    def fake_run(argv, **kwargs):
        calls.append(tuple(str(x) for x in argv))
        command = tuple(str(x) for x in argv[3:])
        if command == ("rev-parse", "HEAD"):
            stdout = b"abc123\n"
        elif command == ("rev-parse", "--abbrev-ref", "HEAD"):
            stdout = b"main\n"
        else:
            stdout = b""
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    state = GitObserver().observe(workcopy, now_ns=10)
    assert state.head_commit == "abc123"
    assert calls == [
        ("git", "-C", str(root.resolve()), "rev-parse", "HEAD"),
        ("git", "-C", str(root.resolve()), "rev-parse", "--abbrev-ref", "HEAD"),
        (
            "git", "-C", str(root.resolve()), "status", "--porcelain=v1", "-z",
            "--untracked-files=all",
        ),
        (
            "git", "-C", str(root.resolve()), "diff", "--no-ext-diff", "--no-textconv",
            "--binary", "HEAD", "--",
        ),
    ]
