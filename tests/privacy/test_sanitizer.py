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


def test_secure_uia_context_redacts_sibling_keystroke_content() -> None:
    event = _event(
        modality="keyboard",
        event_type="key.down",
        payload={
            "key_name": "p",
            "key_char": "p",
            "key_vk": "80",
            "canonical_key_name": "p",
            "canonical_key_char": "p",
            "canonical_key_vk": "80",
            "structural": {
                "role": "PasswordBox",
                "name": "Password",
                "automation_id": "login_password",
            },
        },
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.payload["structural"]["role"] == "PasswordBox"
    assert sanitized.payload["structural"]["automation_id"] == "login_password"
    for field in (
        "key_name",
        "key_char",
        "key_vk",
        "canonical_key_name",
        "canonical_key_char",
        "canonical_key_vk",
    ):
        assert sanitized.payload[field] == "[REDACTED]"
    assert sanitized.privacy_tier is PrivacyTier.SECRET


def test_unverified_keydown_fails_closed_and_redacts_key_content() -> None:
    event = _event(
        modality="keyboard",
        event_type="key.down",
        payload={
            "key_name": "a",
            "key_char": "a",
            "key_vk": "65",
            "canonical_key_char": "a",
        },
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.payload["key_char"] == "[REDACTED]"
    assert sanitized.payload["key_name"] == "[REDACTED]"
    assert sanitized.payload["key_vk"] == "[REDACTED]"
    assert sanitized.payload["canonical_key_char"] == "[REDACTED]"


def test_verified_non_secure_keydown_keeps_character_content() -> None:
    event = _event(
        modality="keyboard",
        event_type="key.down",
        payload={
            "key_name": "a",
            "key_char": "a",
            "structural": {
                "role": "Edit",
                "name": "Code Editor",
                "automation_id": "editor",
            },
        },
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.payload["key_name"] == "a"
    assert sanitized.payload["key_char"] == "a"


def test_keyup_always_drops_redundant_character_content() -> None:
    event = _event(
        modality="keyboard",
        event_type="key.up",
        payload={
            "key_name": "a",
            "key_char": "a",
            "key_vk": "65",
            "structural": {
                "role": "Edit",
                "name": "Code Editor",
                "automation_id": "editor",
            },
        },
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.payload["key_name"] == "[REDACTED]"
    assert sanitized.payload["key_char"] == "[REDACTED]"
    assert sanitized.payload["key_vk"] == "[REDACTED]"


def test_unverified_keytype_redacts_text_and_child_key_content() -> None:
    event = _event(
        modality="keyboard",
        event_type="key.type",
        payload={
            "text": "secret-ish",
            "children": [{"key_char": "s"}, {"key_char": "e"}],
        },
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.payload["text"] == "[REDACTED]"
    assert sanitized.payload["children"][0]["key_char"] == "[REDACTED]"


def test_verified_keydown_is_sensitive_short_retention() -> None:
    event = _event(
        modality="keyboard",
        event_type="key.down",
        payload={
            "key_char": "a",
            "structural": {
                "role": "Edit",
                "name": "Code Editor",
                "automation_id": "editor",
            },
        },
    )

    sanitized = sanitize_event(event, PrivacyPolicy())

    assert sanitized is not None
    assert sanitized.payload["key_char"] == "a"
    assert sanitized.privacy_tier is PrivacyTier.SENSITIVE
    assert sanitized.retention_class is RetentionClass.STRUCTURED_SHORT
