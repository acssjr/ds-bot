from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from queue import Empty, SimpleQueue
from types import MappingProxyType
from typing import Any


class EventKind(str, Enum):
    LIFECYCLE = "lifecycle"
    FRAME = "frame"
    OBSERVATION = "observation"
    INPUT = "input"
    ERROR = "error"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    kind: EventKind
    emitted_at_monotonic: float
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EventKind):
            raise TypeError("kind must be an EventKind")
        if isinstance(self.emitted_at_monotonic, bool) or not isinstance(self.emitted_at_monotonic, Real):
            raise TypeError("timestamp must be a real number")
        if not math.isfinite(self.emitted_at_monotonic):
            raise ValueError("timestamp must be finite")
        if self.emitted_at_monotonic < 0:
            raise ValueError("timestamp must be non-negative")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a Mapping")
        object.__setattr__(self, "payload", _freeze(self.payload))


class EventBus:
    def __init__(self) -> None:
        self._queue: SimpleQueue[RuntimeEvent] = SimpleQueue()

    def publish(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event must be a RuntimeEvent")
        self._queue.put(event)

    def drain(self, limit: int = 1000) -> list[RuntimeEvent]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        events: list[RuntimeEvent] = []
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except Empty:
                break
        return events
