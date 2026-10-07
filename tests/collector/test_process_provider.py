from collections.abc import Iterable

from personal_predictive_ai.collector.process import ProcessCollector, ProcessSample
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


class SnapshotFeed:
    def __init__(self, snapshots: list[list[ProcessSample]]) -> None:
        self._snapshots = iter(snapshots)

    def __call__(self) -> Iterable[ProcessSample]:
        return next(self._snapshots)


def test_process_snapshot_diff_emits_exogenous_start_and_exit() -> None:
    baseline = [ProcessSample(pid=10, create_time=1.0, name="existing.exe")]
    started = baseline + [ProcessSample(pid=20, create_time=2.0, name="job.exe")]
    exited = baseline
    feed = SnapshotFeed([baseline, started, exited])
    collector = ProcessCollector(
        factory=EventFactory(),
        snapshot_provider=feed,
        clock_ns=iter([100, 200]).__next__,
    )
    events = []

    collector.set_publish(events.append)
    assert collector.poll_once() == 0
    assert collector.poll_once() == 1
    assert collector.poll_once() == 1

    assert [event.event_type for event in events] == ["process.started", "process.exited"]
    assert all(event.origin is EventOrigin.EXOGENOUS for event in events)
    assert events[0].process == {"pid": 20, "create_time": 2.0, "name": "job.exe"}
    assert events[1].process == events[0].process
    assert events[1].payload["completion_evidence"] is True


def test_reused_pid_with_new_create_time_is_a_new_process_identity() -> None:
    first = [ProcessSample(pid=42, create_time=1.0, name="old.exe")]
    reused = [ProcessSample(pid=42, create_time=9.0, name="new.exe")]
    collector = ProcessCollector(
        factory=EventFactory(),
        snapshot_provider=SnapshotFeed([first, reused]),
        clock_ns=iter([100, 101]).__next__,
    )
    events = []
    collector.set_publish(events.append)

    collector.poll_once()
    collector.poll_once()

    assert [event.event_type for event in events] == ["process.exited", "process.started"]
    assert events[0].process["create_time"] == 1.0
    assert events[1].process["create_time"] == 9.0
