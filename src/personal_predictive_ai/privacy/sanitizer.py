from __future__ import annotations

from typing import Any

from personal_predictive_ai.events.models import (
    CanonicalEvent,
    PrivacyTier,
    RetentionClass,
)
from personal_predictive_ai.privacy.policy import PrivacyPolicy

_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "authorization",
}
_KEY_CONTENT_KEYS = {
    "text",
    "key_name",
    "key_char",
    "key_vk",
    "canonical_key_name",
    "canonical_key_char",
    "canonical_key_vk",
}
_SECURE_VALUE_KEYS = {
    "value",
    "content",
    "input",
    "input_value",
    *_KEY_CONTENT_KEYS,
}
_SECURE_MARKER_KEYS = {"is_password", "is_secure", "secure", "protected"}
_SECURE_ROLE_KEYS = {"role", "control_type", "type", "name", "automation_id"}


def _dict_is_secure(value: dict[str, Any]) -> bool:
    for key, item in value.items():
        lowered = key.casefold()
        if lowered in _SECURE_MARKER_KEYS and bool(item):
            return True
        if lowered in _SECURE_ROLE_KEYS and isinstance(item, str):
            marker = item.casefold()
            if "password" in marker or "credential" in marker or "secure" in marker:
                return True
    return False


def _contains_secure_marker(value: Any) -> bool:
    if isinstance(value, dict):
        if _dict_is_secure(value):
            return True
        return any(_contains_secure_marker(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_secure_marker(item) for item in value)
    return False


def _sanitize_value(value: Any, *, secure_context: bool = False) -> tuple[Any, bool]:
    if isinstance(value, dict):
        current_secure = secure_context or _contains_secure_marker(value)
        sanitized: dict[str, Any] = {}
        found_secret = False
        for key, item in value.items():
            lowered = key.casefold()
            if lowered in _SENSITIVE_KEYS or (
                current_secure and lowered in _SECURE_VALUE_KEYS
            ):
                sanitized[key] = _REDACTED
                found_secret = True
                continue
            cleaned, child_secret = _sanitize_value(item, secure_context=current_secure)
            sanitized[key] = cleaned
            found_secret = found_secret or child_secret
        return sanitized, found_secret

    if isinstance(value, list):
        items = []
        found_secret = False
        for item in value:
            cleaned, child_secret = _sanitize_value(item, secure_context=secure_context)
            items.append(cleaned)
            found_secret = found_secret or child_secret
        return items, found_secret

    if isinstance(value, tuple):
        items = []
        found_secret = False
        for item in value:
            cleaned, child_secret = _sanitize_value(item, secure_context=secure_context)
            items.append(cleaned)
            found_secret = found_secret or child_secret
        return items, found_secret

    return value, False


def _redact_named_keys(value: Any, keys: set[str]) -> tuple[Any, bool]:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        found = False
        for key, item in value.items():
            if key.casefold() in keys:
                redacted[key] = _REDACTED
                found = True
                continue
            cleaned, child_found = _redact_named_keys(item, keys)
            redacted[key] = cleaned
            found = found or child_found
        return redacted, found
    if isinstance(value, list):
        items = []
        found = False
        for item in value:
            cleaned, child_found = _redact_named_keys(item, keys)
            items.append(cleaned)
            found = found or child_found
        return items, found
    if isinstance(value, tuple):
        items = []
        found = False
        for item in value:
            cleaned, child_found = _redact_named_keys(item, keys)
            items.append(cleaned)
            found = found or child_found
        return items, found
    return value, False


def _keyboard_content_must_be_redacted(event: CanonicalEvent) -> bool:
    if event.modality.casefold() != "keyboard":
        return False
    if event.event_type == "key.up":
        return True
    if event.event_type not in {"key.down", "key.type", "text.input"}:
        return False
    structural = event.payload.get("structural")
    if not isinstance(structural, dict):
        return True
    return _contains_secure_marker(structural)


def sanitize_event(
    event: CanonicalEvent,
    policy: PrivacyPolicy,
) -> CanonicalEvent | None:
    decision = policy.classify(event)
    if decision.drop:
        return None

    payload, payload_secret = _sanitize_value(event.payload)
    if _keyboard_content_must_be_redacted(event):
        payload, keyboard_secret = _redact_named_keys(payload, _KEY_CONTENT_KEYS)
        payload_secret = payload_secret or keyboard_secret

    app, app_secret = _sanitize_value(event.app) if event.app is not None else (None, False)
    process, process_secret = (
        _sanitize_value(event.process) if event.process is not None else (None, False)
    )
    window, window_secret = (
        _sanitize_value(event.window) if event.window is not None else (None, False)
    )
    found_secret = payload_secret or app_secret or process_secret or window_secret

    privacy_tier = decision.privacy_tier
    retention_class = decision.retention_class
    if found_secret:
        privacy_tier = PrivacyTier.SECRET
        retention_class = RetentionClass.STRUCTURED_SHORT

    if (
        payload == event.payload
        and app == event.app
        and process == event.process
        and window == event.window
        and privacy_tier is event.privacy_tier
        and retention_class is event.retention_class
    ):
        return event

    return event.model_copy(
        update={
            "payload": payload,
            "app": app,
            "process": process,
            "window": window,
            "privacy_tier": privacy_tier,
            "retention_class": retention_class,
        }
    )
