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
_SECURE_VALUE_KEYS = {"value", "text", "content", "input", "input_value"}
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


def _sanitize_value(value: Any, *, secure_context: bool = False) -> tuple[Any, bool]:
    if isinstance(value, dict):
        current_secure = secure_context or _dict_is_secure(value)
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


def sanitize_event(
    event: CanonicalEvent,
    policy: PrivacyPolicy,
) -> CanonicalEvent | None:
    decision = policy.classify(event)
    if decision.drop:
        return None

    payload, payload_secret = _sanitize_value(event.payload)
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

