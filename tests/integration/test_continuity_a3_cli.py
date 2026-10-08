from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.cli import main


def _init_task(tmp_path: Path, capsys) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    data_dir = tmp_path / "data"
    code = main([
        "--data-dir", str(data_dir), "continuity-init",
        "--project-key", "p", "--workcopy-root", str(repo),
        "--task-title", "task", "--goal", "old goal",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    return data_dir, payload["task_id"]


def test_continuity_correct_and_evidence_cli(tmp_path: Path, capsys) -> None:
    data_dir, task_id = _init_task(tmp_path, capsys)
    code = main([
        "--data-dir", str(data_dir), "continuity-correct",
        "--task-id", task_id, "--field", "current_goal",
        "--value", "new goal", "--action", "set",
    ])
    assert code == 0
    corrected = json.loads(capsys.readouterr().out)
    assert corrected["snapshot"]["current_goal"] == "new goal"

    code = main([
        "--data-dir", str(data_dir), "continuity-evidence",
        "--task-id", task_id, "--field", "current_goal",
    ])
    assert code == 0
    evidence = json.loads(capsys.readouterr().out)
    assert any(item["content"].get("value") == "new goal" for item in evidence)
    assert all(item["task_id"] == task_id for item in evidence)
