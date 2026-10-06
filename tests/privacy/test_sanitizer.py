import json

from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventOrigin,
    PrivacyTier,
    RetentionClass,
)
from personal_predictive_ai.privacy.policy import PrivacyPolicy
from personal_predictive_ai.privacy.sanitizer import sanitize_event


def _event(**overrides: object) -> CanonicalEvent:
    values = {
        "event_id": "evt-1",
        "timestamp_ns": 1,
        "monotonic_seq": 1,
        "source": "unit",
        "modality": "uia",
        "origin": EventOrigin.ENDOGENOUS,
        "event_type": "ui.input",
        "app": {"name": "editor"},
        "window": {"title": "Project"},
        "payload": {"safe": "value"},
    }
    values.update(overrides)
    return CanonicalEvent(**values)


def test_nested_secure_uia_value_is_removed_but_metadata_remains() -> None:
    event = _event(
        payload={
            "structural": {
                "role": "PasswordBox",
                "name": "Password",
                "value": "hunter2",
                "automation_id": "login_password",
            }
        }
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    serialized = json.dumps(sanitized.model_dump(mode="json"))
    assert "hunter2" not in serialized
    assert sanitized.payload["structural"]["role"] == "PasswordBox"
    assert sanitized.payload["structural"]["automation_id"] == "login_password"
    assert sanitized.privacy_tier is PrivacyTier.SECRET
    assert sanitized.retention_class is RetentionClass.STRUCTURED_SHORT


def test_recursive_credential_like_keys_are_redacted() -> None:
    event = _event(
        payload={
            "request": {
                "api_key": "abc123",
                "nested": {"token": "def456", "label": "safe"},
            }
        }
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    serialized = json.dumps(sanitized.model_dump(mode="json"))
    assert "abc123" not in serialized
    assert "def456" not in serialized
    assert sanitized.payload["request"]["nested"]["label"] == "safe"


def test_clipboard_and_exact_text_are_short_lived_sensitive_data() -> None:
    event = _event(
        modality="clipboard",
        event_type="clipboard.changed",
        payload={"text": "temporary copied text"},
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.privacy_tier is PrivacyTier.SENSITIVE
    assert sanitized.retention_class is RetentionClass.STRUCTURED_SHORT


def test_excluded_application_or_window_is_dropped() -> None:
    policy = PrivacyPolicy(
        excluded_apps={"1password"},
        excluded_window_substrings=("private banking",),
    )

    app_event = _event(app={"name": "1Password"})
    window_event = _event(window={"title": "Private Banking - Browser"})

    assert sanitize_event(app_event, policy) is None
    assert sanitize_event(window_event, policy) is None


def test_explicit_never_store_event_is_dropped() -> None:
    event = _event(retention_class=RetentionClass.NEVER_STORE)
    assert sanitize_event(event, PrivacyPolicy()) is None


def test_non_sensitive_event_is_unchanged() -> None:
    event = _event(payload={"x": 10, "label": "safe"})

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized == event
