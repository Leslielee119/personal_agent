from __future__ import annotations

import io
import time
from collections.abc import Callable
from typing import Any

from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import (
    CanonicalEvent,
    EventActor,
    EventOrigin,
    EventProvenance,
    PrivacyTier,
    RetentionClass,
)
from personal_predictive_ai.storage.raw_ring import RawRing

ScreenshotProvider = Callable[[], Any]
TopologyProvider = Callable[[], dict[str, Any]]


def _default_screenshot_provider() -> Any:
    from openadapt_capture.utils import take_screenshot

    return take_screenshot()


def _default_topology_provider() -> dict[str, Any]:
    from openadapt_capture.desktop_capture import DesktopCaptureScope

    return DesktopCaptureScope.current().snapshot()


class ScreenSnapshotter:
    """Capture a full virtual-desktop image into the short-lived RawRing."""

    def __init__(
        self,
        *,
        factory: EventFactory,
        raw_ring: RawRing,
        screenshot_provider: ScreenshotProvider = _default_screenshot_provider,
        topology_provider: TopologyProvider = _default_topology_provider,
    ) -> None:
        self._factory = factory
        self._raw_ring = raw_ring
        self._screenshot_provider = screenshot_provider
        self._topology_provider = topology_provider

    def capture(
        self,
        *,
        reason: str,
        timestamp_ns: int | None = None,
    ) -> CanonicalEvent:
        image = self._screenshot_provider()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        raw_ref = self._raw_ring.put(buffer.getvalue(), ".png")
        topology = self._topology_provider()

        return self._factory.next(
            timestamp_ns=time.time_ns() if timestamp_ns is None else timestamp_ns,
            source="desktop_screen",
            modality="screen",
            origin=EventOrigin.EXOGENOUS,
            actor=EventActor.SYSTEM,
            provenance=EventProvenance.SYSTEM,
            event_type="screen.snapshot",
            payload={
                "trigger": reason,
                "format": "png",
                "width": int(image.width),
                "height": int(image.height),
                "topology": topology,
            },
            privacy_tier=PrivacyTier.SENSITIVE,
            retention_class=RetentionClass.STRUCTURED_SHORT,
            raw_ref=raw_ref,
        )
