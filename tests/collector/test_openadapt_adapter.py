import json
import sys
import time

import pytest
from openadapt_capture.events import (
    KeyDownEvent,
    KeyTypeEvent,
    MouseClickEvent,
    MouseScrollEvent,
    ScreenFrameEvent,
)
from openadapt_capture.structural import (
    StructuralElement,
    StructuralObservation,
    StructuralObservationRequest,
    StructuralProcessIdentity,
    StructuralTreeNode,
    StructuralWindowIdentity,
    create_structural_observer,
)

from personal_predictive_ai.collector.openadapt import OpenAdaptCollector
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin
from personal_predictive_ai.privacy.policy import PrivacyPolicy
from personal_predictive_ai.privacy.sanitizer import sanitize_event


def _observation(*, secure: bool = False) -> StructuralObservation:
    tree = None
    query_kind = "point"
    element = StructuralElement(role="Button", name="Save")
    if secure:
        query_kind = "window_tree"
        element = StructuralElement(role="PasswordBox", name="Password")
        tree = [StructuralTreeNode(role="PasswordBox", value="hunter2")]
    return StructuralObservation(
        provider="windows_uia",
        event_timestamp=1.0,
        observed_at=1.01,
        query_kind=query_kind,
        element=element,
        process=StructuralProcessIdentity(process_id=123, process_name="editor.exe"),
        window=StructuralWindowIdentity(title="Project - Editor"),
        tree=tree,
        tree_truncated=False if tree is not None else None,
    )


@pytest.mark.parametrize(
    ("upstream", "modality", "event_type"),
    [
        (KeyDownEvent(timestamp=1.0, key_char="a"), "keyboard", "key.down"),
        (KeyTypeEvent(timestamp=1.0, text="abc"), "keyboard", "key.type"),
        (
            MouseClickEvent(timestamp=1.0, x=10, y=20, button="left"),
            "mouse",
            "mouse.singleclick",
        ),
        (
            MouseScrollEvent(timestamp=1.0, x=10, y=20, dx=0, dy=-1),
            "mouse",
            "mouse.scroll",
        ),
        (
            ScreenFrameEvent(timestamp=1.0, width=1920, height=1080),
            "screen",
            "screen.frame",
        ),
    ],
)
def test_openadapt_events_map_to_canonical_endogenous_events(
    upstream, modality: str, event_type: str
) -> None:
    collector = OpenAdaptCollector(factory=EventFactory(), capture_structural=False)

    mapped = collector.translate(upstream)

    assert mapped.source == "openadapt_capture"
    assert mapped.modality == modality
    assert mapped.origin is EventOrigin.ENDOGENOUS
    assert mapped.event_type == event_type
    assert mapped.timestamp_ns == 1_000_000_000
    assert "timestamp" not in mapped.payload
    assert "type" not in mapped.payload


def test_structural_identity_maps_without_leaking_openadapt_types() -> None:
    upstream = KeyDownEvent(timestamp=1.0, key_char="a", structural_observation=_observation())
    collector = OpenAdaptCollector(factory=EventFactory(), capture_structural=False)

    mapped = collector.translate(upstream)

    assert mapped.process == {"pid": 123, "name": "editor.exe"}
    assert mapped.window == {"title": "Project - Editor"}
    assert mapped.payload["structural"]["provider"] == "windows_uia"
    assert not mapped.__class__.__module__.startswith("openadapt_capture")


def test_secure_structural_tree_is_marked_for_canonical_sanitizer() -> None:
    upstream = KeyDownEvent(
        timestamp=1.0,
        key_char="x",
        structural_observation=_observation(secure=True),
    )
    collector = OpenAdaptCollector(factory=EventFactory(), capture_structural=False)

    mapped = collector.translate(upstream)
    sanitized = sanitize_event(mapped, PrivacyPolicy())

    assert sanitized is not None
    serialized = json.dumps(sanitized.model_dump(mode="json"))
    assert "hunter2" not in serialized
    assert "PasswordBox" in serialized


@pytest.mark.slow
def test_windows_native_input_and_uia_smoke() -> None:
    if sys.platform != "win32":
        pytest.skip("Windows native capture qualification")

    observer = create_structural_observer(enabled=True)
    if observer is None:
        pytest.skip("Windows UIA structural observer unavailable")
    try:
        observation = observer.observe(
            StructuralObservationRequest(
                event_timestamp=time.time(),
                action_name="native-smoke",
                query_kind="focused",
            )
        )
    except Exception as exc:
        pytest.skip(f"Windows UIA unavailable: {type(exc).__name__}: {exc}")
    if observation is None:
        pytest.skip("Windows UIA returned no focused-element evidence")

    events = []
    collector = OpenAdaptCollector(factory=EventFactory(), capture_structural=False)
    collector.start(events.append)
    try:
        time.sleep(1.0)
    finally:
        collector.stop()

    health = collector.health()
    assert health.available is True
    assert health.running is False
    if not events:
        pytest.skip(
            "native hook started/stopped but no physical input occurred; "
            "OpenAdapt intentionally filters Windows injected input"
        )
    assert any(event.modality in {"keyboard", "mouse"} for event in events)

