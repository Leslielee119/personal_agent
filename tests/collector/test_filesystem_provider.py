from pathlib import Path

from personal_predictive_ai.collector.filesystem import FilesystemCollector
from personal_predictive_ai.events.ids import EventFactory
from personal_predictive_ai.events.models import EventOrigin


def test_filesystem_changes_normalize_create_modify_delete_move(tmp_path: Path) -> None:
    clock_values = iter([100, 200, 300, 400])
    collector = FilesystemCollector(
        factory=EventFactory(),
        roots=[tmp_path],
        clock_ns=clock_values.__next__,
        debounce_ms=0,
    )
    events = []
    collector.set_publish(events.append)
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"

    collector.observe_change("created", first)
    collector.observe_change("modified", first)
    collector.observe_change("moved", first, second)
    collector.observe_change("deleted", second)

    assert [event.event_type for event in events] == [
        "filesystem.created",
        "filesystem.modified",
        "filesystem.moved",
        "filesystem.deleted",
    ]
    assert all(event.origin is EventOrigin.EXOGENOUS for event in events)
    assert events[2].payload["src_path"] == str(first)
    assert events[2].payload["dest_path"] == str(second)


def test_filesystem_duplicate_burst_is_debounced(tmp_path: Path) -> None:
    clock_values = iter([1_000_000_000, 1_010_000_000, 1_200_000_000])
    collector = FilesystemCollector(
        factory=EventFactory(),
        roots=[tmp_path],
        clock_ns=clock_values.__next__,
        debounce_ms=100,
    )
    events = []
    collector.set_publish(events.append)
    path = tmp_path / "a.txt"

    assert collector.observe_change("modified", path) is True
    assert collector.observe_change("modified", path) is False
    assert collector.observe_change("modified", path) is True

    assert len(events) == 2


def test_filesystem_exclusions_drop_matching_paths(tmp_path: Path) -> None:
    excluded = tmp_path / ".git"
    excluded.mkdir()
    collector = FilesystemCollector(
        factory=EventFactory(),
        roots=[tmp_path],
        excluded_paths=[excluded],
        clock_ns=lambda: 100,
    )
    events = []
    collector.set_publish(events.append)

    accepted = collector.observe_change("created", excluded / "index.lock")

    assert accepted is False
    assert events == []
