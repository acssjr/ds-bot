from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from queue import Empty, SimpleQueue
from types import MappingProxyType
from typing import Any, Mapping


class EventKind(str, Enum):
    LIFECYCLE = "lifecycle"
    FRAME = "frame"
    OBSERVATION = "observation"
    INPUT = "input"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: EventKind
    emitted_at_monotonic: float
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


class EventBus:
    def __init__(self) -> None:
        self._queue: SimpleQueue[RuntimeEvent] = SimpleQueue()

    def publish(self, event: RuntimeEvent) -> None:
        self._queue.put(event)

    def drain(self, limit: int = 1000) -> list[RuntimeEvent]:
        events: list[RuntimeEvent] = []
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                break
        return events
