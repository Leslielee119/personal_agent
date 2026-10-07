from __future__ import annotations

from dataclasses import dataclass

from personal_predictive_ai.events.models import (
    CanonicalEvent,
    PrivacyTier,
    RetentionClass,
)


@dataclass(frozen=True, slots=True)
class PrivacyDecision:
    drop: bool
    privacy_tier: PrivacyTier
    retention_class: RetentionClass
    reason: str = ""


class PrivacyPolicy:
    def __init__(
        self,
        *,
        excluded_apps: set[str] | None = None,
        excluded_window_substrings: tuple[str, ...] = (),
    ) -> None:
        self._excluded_apps = {name.casefold() for name in (excluded_apps or set())}
        self._excluded_window_substrings = tuple(
            value.casefold() for value in excluded_window_substrings
        )

    def classify(self, event: CanonicalEvent) -> PrivacyDecision:
        if event.retention_class is RetentionClass.NEVER_STORE:
            return PrivacyDecision(
                drop=True,
                privacy_tier=event.privacy_tier,
                retention_class=RetentionClass.NEVER_STORE,
                reason="explicit_never_store",
            )

        app_name = str((event.app or {}).get("name", "")).casefold()
        if app_name and app_name in self._excluded_apps:
            return PrivacyDecision(
                drop=True,
                privacy_tier=PrivacyTier.SECRET,
                retention_class=RetentionClass.NEVER_STORE,
                reason="excluded_app",
            )

        window_title = str((event.window or {}).get("title", "")).casefold()
        if window_title and any(
            substring in window_title for substring in self._excluded_window_substrings
        ):
            return PrivacyDecision(
                drop=True,
                privacy_tier=PrivacyTier.SECRET,
                retention_class=RetentionClass.NEVER_STORE,
                reason="excluded_window",
            )

        if event.modality.casefold() in {"clipboard", "text", "keyboard"} or event.event_type in {
            "clipboard.changed",
            "key.type",
            "text.input",
        }:
            return PrivacyDecision(
                drop=False,
                privacy_tier=PrivacyTier.SENSITIVE,
                retention_class=RetentionClass.STRUCTURED_SHORT,
                reason="short_lived_exact_input",
            )

        return PrivacyDecision(
            drop=False,
            privacy_tier=event.privacy_tier,
            retention_class=event.retention_class,
        )
