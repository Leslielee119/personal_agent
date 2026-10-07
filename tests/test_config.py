from pathlib import Path

import pytest

from personal_predictive_ai.config import Settings, load_settings


def test_settings_defaults_are_local_and_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in (
        "PPA_DATA_DIR",
        "PPA_RAW_TTL_SECONDS",
        "PPA_STRUCTURED_RETENTION_DAYS",
        "PPA_OFFLINE_MODE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.data_dir == Path("data")
    assert settings.raw_ttl_seconds == 900
    assert settings.structured_retention_days == 30
    assert settings.offline_mode is True


def test_environment_overrides_parse_without_side_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PPA_DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("PPA_RAW_TTL_SECONDS", "120")
    monkeypatch.setenv("PPA_STRUCTURED_RETENTION_DAYS", "7")
    monkeypatch.setenv("PPA_OFFLINE_MODE", "false")

    settings = load_settings()

    assert settings.data_dir == tmp_path / "custom"
    assert settings.raw_ttl_seconds == 120
    assert settings.structured_retention_days == 7
    assert settings.offline_mode is False
