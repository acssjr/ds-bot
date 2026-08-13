from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from threading import Lock
from types import MappingProxyType
from typing import Any, Protocol


class EventKind(str, Enum):
    LIFECYCLE = "lifecycle"
    FRAME = "frame"
    OBSERVATION = "observation"
    INPUT = "input"
    ERROR = "error"


class EventSink(Protocol):
    def publish(self, event: "RuntimeEvent") -> None: ...


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
    """Bounded, non-blocking event sink that drops the oldest retained event."""

    def __init__(self, capacity: int = 1000) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise TypeError("capacity must be an integer")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._queue: deque[RuntimeEvent] = deque()
        self._dropped_count = 0
        self._lock = Lock()

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped_count

    def publish(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event must be a RuntimeEvent")
        with self._lock:
            if len(self._queue) == self._capacity:
                self._queue.popleft()
                self._dropped_count += 1
            self._queue.append(event)

    def drain(self, limit: int = 1000) -> list[RuntimeEvent]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            count = min(limit, len(self._queue))
            return [self._queue.popleft() for _ in range(count)]


class LoggingEventSink:
    """Synchronous CLI sink; events are logged as they are produced, never buffered."""

    def __init__(self, logger: Any) -> None:
        self._logger = logger

    def publish(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event must be a RuntimeEvent")
        self._logger.info("{} | {}", event.kind.value, dict(event.payload))
