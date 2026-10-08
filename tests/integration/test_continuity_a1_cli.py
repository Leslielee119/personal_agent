from __future__ import annotations

import json
from pathlib import Path

from personal_predictive_ai.cli import main


def test_continuity_init_and_resume_cli(tmp_path: Path, capsys) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    data_dir = tmp_path / "data"
    code = main([
        "--data-dir", str(data_dir),
        "continuity-init",
        "--project-key", "personal_agent",
        "--workcopy-root", str(repo),
        "--task-title", "Task Continuity",
        "--goal", "Ship A1",
        "--last-position", "Registry complete",
        "--next-step", "Dogfood resume",
    ])
    assert code == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["project_id"].startswith("project:")
    assert init_payload["workcopy_id"].startswith("workcopy:")
    assert init_payload["task_id"].startswith("task:")

    code = main([
        "--data-dir", str(data_dir),
        "continuity-resume",
        "--task-id", init_payload["task_id"],
    ])
    assert code == 0
    text = capsys.readouterr().out
    assert "当前任务" in text
    assert "Ship A1" in text
    assert "Dogfood resume" in text

    code = main([
        "--data-dir", str(data_dir),
        "continuity-resume",
        "--task-id", init_payload["task_id"],
        "--format", "json",
    ])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["snapshot"]["snapshot_id"].startswith("snapshot:")
    assert payload["brief"]["evidence_ids"]
