import json
from pathlib import Path

from personal_predictive_ai.collector.base import CollectorHealth
from personal_predictive_ai.config import Settings
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin
from personal_predictive_ai.runtime.service import CaptureService


class FixtureCollector:
    def __init__(self, name, events=None, *, fail_start=False):
        self.name = name
        self.events = list(events or [])
        self.fail_start = fail_start
        self.running = False

    def start(self, publish):
        if self.fail_start:
            raise RuntimeError("fixture provider failure")
        self.running = True
        for event in self.events:
            publish(event)

    def stop(self):
        self.running = False

    def health(self):
        return CollectorHealth(available=True, running=self.running)


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path, raw_ttl_seconds=1, offline_mode=True)


def test_end_to_end_pipeline_is_ordered_private_and_fault_isolated(tmp_path: Path) -> None:
    factory = EventFactory()
    endogenous = factory.next(
        timestamp_ns=200,
        source="fixture_input",
        modality="keyboard",
        origin=EventOrigin.ENDOGENOUS,
        event_type="key.type",
        payload={"text": "hello"},
    )
    secure = factory.next(
        timestamp_ns=200,
        source="fixture_uia",
        modality="uia",
        origin=EventOrigin.ENDOGENOUS,
        event_type="uia.focused",
        payload={
            "structural": {
                "role": "PasswordBox",
                "name": "Password",
                "value": "pipeline-secret",
                "automation_id": "login_password",
            }
        },
    )
    exogenous = factory.next(
        timestamp_ns=100,
        source="fixture_process",
        modality="process",
        origin=EventOrigin.EXOGENOUS,
        event_type="process.exited",
        payload={"completion_evidence": True},
    )

    service = CaptureService(
        settings=_settings(tmp_path),
        collectors=[
            FixtureCollector("input", [endogenous, secure]),
            FixtureCollector("broken", fail_start=True),
            FixtureCollector("process", [exogenous]),
        ],
        event_factory=factory,
    )
    raw_ref = service.raw_ring.put(b"temporary pixels", ".bin")

    service.start()
    status = service.status()
    created_ns = int(raw_ref.split("-", 1)[0])
    service.expire_raw(now_ns=created_ns + 2_000_000_000)
    events = list(service.event_store.iter_events())
    serialized = json.dumps([event.model_dump(mode="json") for event in events])

    assert status.running is True
    assert "broken" in status.provider_errors
    assert [event.timestamp_ns for event in events] == [100, 200, 200]
    assert [event.monotonic_seq for event in events] == [3, 1, 2]
    assert "pipeline-secret" not in serialized
    assert "PasswordBox" in serialized
    assert service.raw_ring.resolve(raw_ref) is None
    assert service.event_store.integrity_check() == "ok"

    service.stop()
    assert service.status().running is False
