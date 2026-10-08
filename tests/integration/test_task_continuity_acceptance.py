from __future__ import annotations

import json
import subprocess
from pathlib import Path

from personal_predictive_ai.cli import main
from personal_predictive_ai.storage.continuity_store import ContinuityStore


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _two_workcopies(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    _git(a, "init")
    _git(a, "config", "user.email", "test@example.com")
    _git(a, "config", "user.name", "Test User")
    (a / "work.txt").write_text("base\n", encoding="utf-8")
    _git(a, "add", "work.txt")
    _git(a, "commit", "-m", "initial")
    _git(a, "worktree", "add", "-b", "task-b", str(b))
    return a, b


def _json_cli(capsys, args: list[str]) -> dict | list:
    code = main(args)
    assert code == 0
    return json.loads(capsys.readouterr().out)


def _init_task(
    capsys,
    data_dir: Path,
    root: Path,
    *,
    title: str,
    goal: str,
) -> str:
    payload = _json_cli(capsys, [
        "--data-dir", str(data_dir), "continuity-init",
        "--project-key", "personal_agent",
        "--workcopy-root", str(root),
        "--task-title", title,
        "--goal", goal,
        "--last-position", f"{title} position",
        "--next-step", f"{title} next",
    ])
    assert isinstance(payload, dict)
    return str(payload["task_id"])


def _correct(
    capsys,
    data_dir: Path,
    task_id: str,
    field: str,
    value: str,
    action: str,
) -> None:
    payload = _json_cli(capsys, [
        "--data-dir", str(data_dir), "continuity-correct",
        "--task-id", task_id, "--field", field,
        "--value", value, "--action", action,
    ])
    assert isinstance(payload, dict)


def _record_result(
    capsys,
    data_dir: Path,
    task_id: str,
    outcome: str,
) -> dict:
    payload = _json_cli(capsys, [
        "--data-dir", str(data_dir), "continuity-record-result",
        "--task-id", task_id,
        "--check-kind", "pytest",
        "--outcome", outcome,
        "--scope", "pytest -q",
    ])
    assert isinstance(payload, dict)
    return payload


def _resume_json(capsys, data_dir: Path, task_id: str) -> dict:
    payload = _json_cli(capsys, [
        "--data-dir", str(data_dir), "continuity-resume",
        "--task-id", task_id, "--format", "json",
    ])
    assert isinstance(payload, dict)
    return payload


def _resume_text(capsys, data_dir: Path, task_id: str) -> str:
    code = main([
        "--data-dir", str(data_dir), "continuity-resume",
        "--task-id", task_id,
    ])
    assert code == 0
    return capsys.readouterr().out


def test_frozen_cross_worktree_task_continuity_acceptance(tmp_path: Path, capsys) -> None:
    a_root, b_root = _two_workcopies(tmp_path)
    data_dir = tmp_path / "data"
    a_task = _init_task(capsys, data_dir, a_root, title="A task", goal="A goal")
    b_task = _init_task(capsys, data_dir, b_root, title="B task", goal="B goal")
    _correct(capsys, data_dir, a_task, "blockers", "A blocker", "add")
    _correct(capsys, data_dir, b_task, "blockers", "B blocker", "add")
    a_result = _record_result(capsys, data_dir, a_task, "pass")
    b_result = _record_result(capsys, data_dir, b_task, "fail")

    a_text = _resume_text(capsys, data_dir, a_task)
    assert "A goal" in a_text and "A blocker" in a_text
    assert "B goal" not in a_text and "B blocker" not in a_text
    b_text = _resume_text(capsys, data_dir, b_task)
    assert "B goal" in b_text and "B blocker" in b_text
    assert "A goal" not in b_text and "A blocker" not in b_text

    a_json = _resume_json(capsys, data_dir, a_task)
    b_json = _resume_json(capsys, data_dir, b_task)
    assert a_result["result_id"] in a_json["snapshot"]["verified_result_ids"]
    assert b_result["result_id"] in b_json["snapshot"]["verified_result_ids"]
    assert set(a_json["snapshot"]["verification_applicability"].values()) == {"current"}
    assert set(b_json["snapshot"]["verification_applicability"].values()) == {"current"}

    (a_root / "work.txt").write_text("changed\n", encoding="utf-8")
    stale = _resume_json(capsys, data_dir, a_task)
    assert set(stale["snapshot"]["verification_applicability"].values()) == {
        "needs_revalidation"
    }
    assert "上次通过，当前状态尚未复验" in _resume_text(capsys, data_dir, a_task)

    _correct(capsys, data_dir, a_task, "current_goal", "A corrected goal", "set")
    assert "A corrected goal" in _resume_text(capsys, data_dir, a_task)
    assert "B goal" in _resume_text(capsys, data_dir, b_task)

    sentinel = "ACCEPTANCE-DELETE-SECRET-93b7"
    _correct(capsys, data_dir, a_task, "blockers", sentinel, "add")
    assert sentinel in _resume_text(capsys, data_dir, a_task)
    evidence = _json_cli(capsys, [
        "--data-dir", str(data_dir), "continuity-evidence",
        "--task-id", a_task, "--field", "blockers",
    ])
    assert isinstance(evidence, list)
    target = next(item for item in evidence if item["content"].get("value") == sentinel)
    _json_cli(capsys, [
        "--data-dir", str(data_dir), "continuity-forget",
        "--scope", "evidence", "--id", target["evidence_id"],
    ])
    assert sentinel not in _resume_text(capsys, data_dir, a_task)
    assert "B blocker" in _resume_text(capsys, data_dir, b_task)

    db_path = data_dir / "continuity.db"
    store = ContinuityStore(db_path)
    try:
        assert all(
            sentinel not in str(item.model_dump(mode="json"))
            for item in store.iter_snapshots(a_task)
        )
        assert all(
            sentinel not in str(item.model_dump(mode="json"))
            for item in store.iter_briefs(a_task)
        )
        assert store.get_task(b_task) is not None
    finally:
        store.close()
    raw = sentinel.encode("utf-8")
    for candidate in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        if candidate.exists():
            assert raw not in candidate.read_bytes()


def test_resume_fails_closed_when_git_observation_is_unavailable(tmp_path: Path, capsys) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test User")
    (root / "work.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "work.txt")
    _git(root, "commit", "-m", "initial")
    data_dir = tmp_path / "data"
    task_id = _init_task(capsys, data_dir, root, title="task", goal="goal")
    _record_result(capsys, data_dir, task_id, "pass")

    git_dir = root / ".git"
    broken = root / ".git-broken"
    git_dir.rename(broken)
    try:
        payload = _resume_json(capsys, data_dir, task_id)
    finally:
        broken.rename(git_dir)

    assert set(payload["snapshot"]["verification_applicability"].values()) == {
        "unsupported"
    }
