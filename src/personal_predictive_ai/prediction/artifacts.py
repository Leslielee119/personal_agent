from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ARTIFACT_FILENAMES = (
    "dataset_manifest.json",
    "validity_audit.json",
    "split_manifest.json",
    "baseline_predictions.jsonl",
    "metrics.json",
    "ablation.json",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def write_json(path: Path, value: Any) -> None:
    path.write_text(_canonical_json(value) + "\n", encoding="utf-8", newline="\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "".join(_canonical_json(row) + "\n" for row in rows)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_benchmark_artifacts(
    output_root: str | Path,
    *,
    run_id: str,
    dataset_manifest: dict[str, Any],
    validity_audit: dict[str, Any],
    split_manifest: dict[str, Any],
    baseline_predictions: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    ablation: dict[str, Any],
) -> Path:
    root = Path(output_root) / "prediction_runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "dataset_manifest.json", dataset_manifest)
    write_json(root / "validity_audit.json", validity_audit)
    write_json(root / "split_manifest.json", split_manifest)
    write_jsonl(root / "baseline_predictions.jsonl", baseline_predictions)
    write_json(root / "metrics.json", metrics)
    write_json(root / "ablation.json", ablation)
    return root
