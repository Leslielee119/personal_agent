from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from personal_predictive_ai.skills.models import (
    RiskClass,
    SkillDraft,
    SkillKind,
    SkillProjectionManifest,
    SkillRecord,
    SkillScope,
    VerificationSpec,
)
from personal_predictive_ai.skills.registry import TrustedRegistryService
from personal_predictive_ai.skills.safety import validate_safe_structured_text

_SCHEMA = "ppa.skill-projection-md/v1"
_FRONTMATTER_KEYS = {
    "schema_version",
    "skill_id",
    "version",
    "canonical_name",
    "kind",
    "status",
    "risk_class",
    "scope",
    "source_package_id",
}
_SECTION_ORDER = (
    "Purpose",
    "Initiation",
    "Preconditions",
    "Parameters",
    "Procedure",
    "Capabilities",
    "Termination",
    "Success",
    "Verification",
    "Evidence Summary",
)


class ProjectionValidationError(ValueError):
    pass

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_block(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )
    return f"```json\n{payload}\n```"


def _frontmatter(record: SkillRecord) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA,
        "skill_id": record.skill_id,
        "version": record.version,
        "canonical_name": record.canonical_name,
        "kind": record.kind.value,
        "status": record.status.value,
        "risk_class": record.risk_class.value,
        "scope": record.scope.model_dump(mode="json"),
        "source_package_id": record.source_package_id,
    }


def render_skill_markdown(record: SkillRecord) -> str:
    meta = yaml.safe_dump(
        _frontmatter(record),
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
    ).strip()
    evidence = {
        "evidence_refs": record.evidence_refs,
        "contradiction_refs": record.contradiction_refs,
        "provenance_summary": record.provenance_summary,
        "support_sessions": record.support_sessions,
        "confidence": record.confidence,
    }
    sections = {
        "Purpose": record.purpose,
        "Initiation": record.initiation_conditions,
        "Preconditions": record.preconditions,
        "Parameters": record.parameters,
        "Procedure": record.procedure_steps,
        "Capabilities": record.required_capabilities,
        "Termination": record.termination_conditions,
        "Success": record.success_conditions,
        "Verification": record.verification_spec.model_dump(mode="json"),
        "Evidence Summary": evidence,
    }
    body = ["---", meta, "---", f"# {record.name}"]
    for heading in _SECTION_ORDER:
        body.extend(["", f"## {heading}", _json_block(sections[heading])])
    return "\n".join(body) + "\n"


def _split_projection(text: str) -> tuple[dict[str, Any], str, dict[str, str]]:
    if not text.startswith("---\n"):
        raise ProjectionValidationError("missing YAML frontmatter")
    try:
        _, yaml_text, body = text.split("---\n", 2)
        meta = yaml.safe_load(yaml_text)
    except (ValueError, yaml.YAMLError) as exc:
        raise ProjectionValidationError("invalid YAML frontmatter") from exc
    if not isinstance(meta, dict) or set(meta) != _FRONTMATTER_KEYS:
        raise ProjectionValidationError("frontmatter fields do not match schema")
    if meta.get("schema_version") != _SCHEMA:
        raise ProjectionValidationError("unsupported projection schema")

    lines = body.strip().splitlines()
    if not lines or not lines[0].startswith("# "):
        raise ProjectionValidationError("missing skill title")
    name = lines[0][2:].strip()
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in lines[1:]:
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            if current in sections:
                raise ProjectionValidationError("duplicate section")
            buffer = []
            continue
        if current is None:
            if line.strip():
                raise ProjectionValidationError("content before first section")
            continue
        buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    if tuple(sections) != _SECTION_ORDER:
        raise ProjectionValidationError("projection sections do not match schema")
    if not name:
        raise ProjectionValidationError("skill title cannot be empty")
    return meta, name, sections


def _decode_json_block(content: str, section: str) -> Any:
    lines = content.splitlines()
    if len(lines) < 3 or lines[0] != "```json" or lines[-1] != "```":
        raise ProjectionValidationError(f"{section} must be a JSON code block")
    payload = "\n".join(lines[1:-1])
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProjectionValidationError(f"invalid JSON in {section}") from exc


def _parse_projection(text: str) -> tuple[dict[str, Any], SkillDraft]:
    meta, name, sections = _split_projection(text)
    try:
        if not isinstance(meta["skill_id"], str) or not meta["skill_id"]:
            raise ValueError("invalid skill_id")
        if not isinstance(meta["version"], int) or meta["version"] < 1:
            raise ValueError("invalid version")
        canonical_name = str(meta["canonical_name"])
        if not canonical_name:
            raise ValueError("invalid canonical_name")
        kind = SkillKind(meta["kind"])
        risk_class = RiskClass(meta["risk_class"])
        scope = SkillScope.model_validate(meta["scope"])
        source_package_id = meta["source_package_id"]
        if source_package_id is not None and not isinstance(source_package_id, str):
            raise ValueError("invalid source_package_id")
        purpose = _decode_json_block(sections["Purpose"], "Purpose")
        evidence = _decode_json_block(sections["Evidence Summary"], "Evidence Summary")
        if not isinstance(evidence, dict) or set(evidence) != {
            "evidence_refs",
            "contradiction_refs",
            "provenance_summary",
            "support_sessions",
            "confidence",
        }:
            raise ProjectionValidationError("invalid Evidence Summary")
        draft = SkillDraft(
            canonical_name=canonical_name,
            name=name,
            kind=kind,
            purpose=purpose,
            initiation_conditions=_decode_json_block(sections["Initiation"], "Initiation"),
            preconditions=_decode_json_block(sections["Preconditions"], "Preconditions"),
            parameters=_decode_json_block(sections["Parameters"], "Parameters"),
            procedure_steps=_decode_json_block(sections["Procedure"], "Procedure"),
            required_capabilities=_decode_json_block(sections["Capabilities"], "Capabilities"),
            termination_conditions=_decode_json_block(sections["Termination"], "Termination"),
            success_conditions=_decode_json_block(sections["Success"], "Success"),
            verification_spec=VerificationSpec.model_validate(
                _decode_json_block(sections["Verification"], "Verification")
            ),
            scope=scope,
            risk_class=risk_class,
            evidence_refs=evidence["evidence_refs"],
            contradiction_refs=evidence["contradiction_refs"],
            provenance_summary=evidence["provenance_summary"],
            support_sessions=evidence["support_sessions"],
            confidence=evidence["confidence"],
            source_package_id=source_package_id,
        )
        validate_safe_structured_text(draft.model_dump(mode="json"))
    except ProjectionValidationError:
        raise
    except (ValidationError, ValueError, TypeError) as exc:
        raise ProjectionValidationError("projection payload is invalid") from exc
    return meta, draft


def parse_skill_markdown(text: str) -> SkillDraft:
    return _parse_projection(text)[1]

def projection_manifest_for(
    record: SkillRecord,
    *,
    output_path: Path,
    content: str,
) -> SkillProjectionManifest:
    content_hash = f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"
    identity = json.dumps(
        {
            "skill_id": record.skill_id,
            "version": record.version,
            "output_path": str(output_path),
            "content_hash": content_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    projection_id = f"projection:{hashlib.sha256(identity).hexdigest()}"
    return SkillProjectionManifest(
        projection_id=projection_id,
        skill_id=record.skill_id,
        version=record.version,
        output_path=str(output_path),
        content_hash=content_hash,
        created_at=_utc_now(),
    )


def _draft_from_record(record: SkillRecord) -> SkillDraft:
    return SkillDraft(
        **record.model_dump(
            exclude={
                "schema_version",
                "skill_id",
                "version",
                "status",
                "valid_from",
                "valid_to",
                "supersedes",
                "created_by",
                "created_at",
            }
        )
    )

def proposal_from_projection_edit(
    service: TrustedRegistryService,
    base: SkillRecord,
    text: str,
    *,
    proposed_by: str,
):
    meta, proposed = _parse_projection(text)
    if meta["skill_id"] != base.skill_id or meta["version"] != base.version:
        raise ProjectionValidationError("projection identity/version mismatch")
    if meta["status"] != base.status.value:
        raise ProjectionValidationError("status is machine-controlled in E1")
    if proposed.canonical_name != base.canonical_name:
        raise ProjectionValidationError("canonical_name cannot change in E1")
    if proposed.kind is not base.kind or proposed.scope != base.scope:
        raise ProjectionValidationError("skill identity fields cannot change in E1")
    if proposed.source_package_id != base.source_package_id:
        raise ProjectionValidationError("source package is machine-controlled")

    machine_fields = (
        "evidence_refs",
        "contradiction_refs",
        "provenance_summary",
        "support_sessions",
        "confidence",
    )
    for field in machine_fields:
        if getattr(proposed, field) != getattr(base, field):
            raise ProjectionValidationError(f"{field} is machine-controlled")

    current = _draft_from_record(base)
    current_data = current.model_dump(mode="json")
    proposed_data = proposed.model_dump(mode="json")
    if current_data == proposed_data:
        return None
    patch = {
        key: value
        for key, value in proposed_data.items()
        if key != "schema_version" and value != current_data.get(key)
    }
    return service.stage_skill_update(base.skill_id, patch, proposed_by=proposed_by)
