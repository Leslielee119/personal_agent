from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from personal_predictive_ai.events.models import CanonicalEvent

PublishCallback = Callable[[CanonicalEvent], object]


@dataclass(frozen=True, slots=True)
class CollectorHealth:
    available: bool
    running: bool
    detail: str = ""
    events_published: int = 0
    structural_available: bool = False
    structural_observations: int = 0


class Collector(Protocol):
    def start(self, publish: PublishCallback) -> None: ...

    def stop(self) -> None: ...

    def health(self) -> CollectorHealth: ...
