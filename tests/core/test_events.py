from src.core.events import EventBus, EventKind, RuntimeEvent


def test_event_bus_preserves_fifo_order() -> None:
    bus = EventBus()
    bus.publish(RuntimeEvent(EventKind.FRAME, 1.0, {"frame_id": 1}))
    bus.publish(RuntimeEvent(EventKind.OBSERVATION, 2.0, {"frame_id": 1}))
    assert [event.kind for event in bus.drain()] == [EventKind.FRAME, EventKind.OBSERVATION]
    assert bus.drain() == []
