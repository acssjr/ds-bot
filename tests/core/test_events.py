import math

import pytest

from src.core.events import EventBus, EventKind, LoggingEventSink, RuntimeEvent


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


def test_event_bus_drops_oldest_at_capacity_and_reports_count() -> None:
    bus = EventBus(capacity=2)
    for frame_id in range(1, 4):
        bus.publish(RuntimeEvent(EventKind.FRAME, float(frame_id), {"frame_id": frame_id}))

    assert bus.dropped_count == 1
    assert [event.payload["frame_id"] for event in bus.drain()] == [2, 3]


@pytest.mark.parametrize("capacity", [True, 0, -1, 1.5])
def test_event_bus_rejects_invalid_capacity(capacity) -> None:
    with pytest.raises((TypeError, ValueError), match="capacity"):
        EventBus(capacity=capacity)


def test_logging_sink_logs_each_event_immediately() -> None:
    messages = []

    class Logger:
        def info(self, *args):
            messages.append(args)

    sink = LoggingEventSink(Logger())
    sink.publish(RuntimeEvent(EventKind.FRAME, 1.0, {"frame_id": 7}))

    assert messages == [("{} | {}", "frame", {"frame_id": 7})]


@pytest.mark.parametrize("limit", [True, 0, -1, 1.5, math.nan])
def test_event_bus_rejects_invalid_drain_limit(limit) -> None:
    with pytest.raises((TypeError, ValueError), match="limit"):
        EventBus().drain(limit)
