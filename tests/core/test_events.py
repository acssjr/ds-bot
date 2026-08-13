import math

import pytest

from src.core.events import EventBus, EventKind, RuntimeEvent


def test_event_bus_preserves_fifo_order() -> None:
    bus = EventBus()
    bus.publish(RuntimeEvent(EventKind.FRAME, 1.0, {"frame_id": 1}))
    bus.publish(RuntimeEvent(EventKind.OBSERVATION, 2.0, {"frame_id": 1}))
    assert [event.kind for event in bus.drain()] == [EventKind.FRAME, EventKind.OBSERVATION]
    assert bus.drain() == []


def test_runtime_event_deeply_detaches_mutable_payload() -> None:
    original = {"nested": {"items": [1, 2]}, "tags": {"a", "b"}}
    event = RuntimeEvent(EventKind.OBSERVATION, 1.0, original)
    original["nested"]["items"].append(3)
    assert event.payload["nested"]["items"] == (1, 2)
    with pytest.raises(TypeError):
        event.payload["nested"]["new"] = True
    assert event.payload["tags"] == frozenset({"a", "b"})


@pytest.mark.parametrize("kind", ["frame", None])
def test_runtime_event_requires_event_kind(kind) -> None:
    with pytest.raises(TypeError, match="EventKind"):
        RuntimeEvent(kind, 1.0, {})


@pytest.mark.parametrize("timestamp", [True, -1.0, math.nan, math.inf, object()])
def test_runtime_event_rejects_invalid_timestamp(timestamp) -> None:
    with pytest.raises((TypeError, ValueError), match="timestamp"):
        RuntimeEvent(EventKind.FRAME, timestamp, {})


def test_event_bus_rejects_non_event() -> None:
    with pytest.raises(TypeError, match="RuntimeEvent"):
        EventBus().publish(object())


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5, math.nan])
def test_event_bus_rejects_invalid_drain_limit(limit) -> None:
    with pytest.raises((TypeError, ValueError), match="limit"):
        EventBus().drain(limit)
