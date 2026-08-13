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
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("payload floats must be finite")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("payload mapping keys must be strings")
            frozen[key] = _freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    raise TypeError(f"unsupported payload value: {type(value).__name__}")


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
        timestamp = float(self.emitted_at_monotonic)
        if not math.isfinite(timestamp):
            raise ValueError("timestamp must be finite")
        if timestamp < 0:
            raise ValueError("timestamp must be non-negative")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a Mapping")
        object.__setattr__(self, "emitted_at_monotonic", timestamp)
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
        self._latest_lifecycle: RuntimeEvent | None = None
        self._latest_error: RuntimeEvent | None = None

    @property
    def dropped_count(self) -> int:
        with self._lock:
            return self._dropped_count

    @property
    def latest_lifecycle(self) -> RuntimeEvent | None:
        with self._lock:
            return self._latest_lifecycle

    @property
    def latest_error(self) -> RuntimeEvent | None:
        with self._lock:
            return self._latest_error

    @staticmethod
    def _is_control(event: RuntimeEvent) -> bool:
        return event.kind in {EventKind.LIFECYCLE, EventKind.ERROR, EventKind.INPUT}

    def _drop_oldest(self, predicate) -> bool:
        for index, queued in enumerate(self._queue):
            if predicate(queued):
                del self._queue[index]
                self._dropped_count += 1
                return True
        return False

    def publish(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event must be a RuntimeEvent")
        with self._lock:
            if event.kind is EventKind.LIFECYCLE:
                self._latest_lifecycle = event
            elif event.kind is EventKind.ERROR:
                self._latest_error = event
            if len(self._queue) == self._capacity:
                if self._is_control(event):
                    if not self._drop_oldest(lambda queued: not self._is_control(queued)):
                        self._queue.popleft()
                        self._dropped_count += 1
                elif not self._drop_oldest(lambda queued: not self._is_control(queued)):
                    self._dropped_count += 1
                    return
            self._queue.append(event)

    def drain(self, limit: int = 1000) -> list[RuntimeEvent]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if limit <= 0:
            raise ValueError("limit must be positive")
        with self._lock:
            count = min(limit, len(self._queue))
            return [self._queue.popleft() for _ in range(count)]

    def reset(self) -> None:
        """Clear all per-session retained events and authoritative snapshots."""
        with self._lock:
            self._queue.clear()
            self._dropped_count = 0
            self._latest_lifecycle = None
            self._latest_error = None


class LoggingEventSink:
    """Synchronous CLI sink; events are logged as they are produced, never buffered."""

    def __init__(self, logger: Any) -> None:
        self._logger = logger

    def publish(self, event: RuntimeEvent) -> None:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event must be a RuntimeEvent")
        self._logger.info("{} | {}", event.kind.value, dict(event.payload))
