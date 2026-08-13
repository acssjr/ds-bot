import threading

import numpy as np
import pytest

from src.capture.manager import CaptureManager
from src.capture.models import CaptureBackend, CapturedImage
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind, RuntimeEvent
from src.core.lifecycle import Lifecycle, RuntimeStatus
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.vision.pipeline import VisionPipeline


class Source:
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def capture(self):
        return CapturedImage(np.zeros((2, 2, 3), dtype=np.uint8), 1.0, CaptureBackend.REPLAY)

    def stop(self):
        self.stopped = True


class Perception:
    def analyze(self, image):
        return {"screen": "UNKNOWN"}


def runtime(source, *, clock, events=None):
    return BotRuntime(
        capture=CaptureManager(source, device_serial="replay", connection_generation=lambda: 0, clock=lambda: 1.0),
        perception=Perception(),
        events=events or EventBus(),
        lifecycle=Lifecycle(),
        cancellation=CancellationToken(),
        settings=RuntimeSettings(0.0),
        clock=clock,
    )


def test_invalid_clock_cannot_prevent_stop_or_failed_lifecycle() -> None:
    source = Source()
    bot = runtime(source, clock=lambda: float("nan"))

    with pytest.raises(ValueError, match="timestamp"):
        bot.run(max_frames=1)

    assert source.stopped
    assert bot._lifecycle.status is RuntimeStatus.FAILED


def test_lifecycle_events_fall_back_when_clock_raises() -> None:
    source = Source()
    events = EventBus()
    bot = runtime(source, clock=lambda: (_ for _ in ()).throw(RuntimeError("clock broken")), events=events)

    with pytest.raises(RuntimeError, match="clock broken"):
        bot.run(max_frames=1)

    assert source.stopped
    assert bot._lifecycle.status is RuntimeStatus.FAILED
    assert any(event.kind is EventKind.LIFECYCLE for event in events.drain())


def test_invalid_clock_at_starting_stopping_and_stopped_uses_control_fallback() -> None:
    values = iter([float("nan"), 1.0, 1.0, 1.0, float("nan"), float("nan")])
    source = Source()
    events = EventBus()
    bot = runtime(source, clock=lambda: next(values), events=events)

    assert bot.run(max_frames=1) == 1
    assert source.stopped
    assert bot._lifecycle.status is RuntimeStatus.STOPPED
    assert [event.kind for event in events.drain()] == [
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
        EventKind.FRAME,
        EventKind.OBSERVATION,
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
    ]


def test_runtime_event_rejects_cross_thread_mutable_or_unknown_values() -> None:
    class Custom:
        pass

    for invalid in (np.zeros((1, 1)), bytearray(b"x"), Custom(), {1: "bad"}, float("nan")):
        with pytest.raises((TypeError, ValueError)):
            RuntimeEvent(EventKind.FRAME, 1.0, {"value": invalid})


def test_event_bus_keeps_control_events_when_telemetry_floods() -> None:
    bus = EventBus(capacity=3)
    for index in range(10):
        bus.publish(RuntimeEvent(EventKind.FRAME, float(index + 1), {"frame_id": index}))
    bus.publish(RuntimeEvent(EventKind.LIFECYCLE, 11.0, {"status": "running"}))
    bus.publish(RuntimeEvent(EventKind.ERROR, 12.0, {"phase": "run", "error": "x"}))

    kinds = [event.kind for event in bus.drain()]
    assert EventKind.LIFECYCLE in kinds
    assert EventKind.ERROR in kinds
    assert bus.dropped_count >= 9


def test_event_bus_is_safe_for_concurrent_publish_and_drain() -> None:
    bus = EventBus(capacity=32)
    errors = []

    def publish():
        try:
            for index in range(500):
                bus.publish(RuntimeEvent(EventKind.FRAME, float(index + 1), {"frame_id": index}))
        except Exception as exc:
            errors.append(exc)

    def drain():
        try:
            for _ in range(100):
                bus.drain()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=publish), threading.Thread(target=drain)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


def test_only_one_concurrent_run_can_start_capture() -> None:
    source = Source()
    bot = runtime(source, clock=lambda: 1.0)
    results = []

    def run():
        try:
            results.append(bot.run(max_frames=1))
        except Exception as exc:
            results.append(exc)

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(1) == 1
    assert sum(isinstance(result, RuntimeError) for result in results) == 1


def test_runtime_passes_cancellation_to_cooperative_perception() -> None:
    seen = []

    class CooperativePerception:
        def analyze(self, image, *, cancellation):
            seen.append(cancellation)
            return {"screen": "UNKNOWN"}

    source = Source()
    token = CancellationToken()
    bot = BotRuntime(
        capture=CaptureManager(source, device_serial="replay", connection_generation=lambda: 0, clock=lambda: 1.0),
        perception=CooperativePerception(),
        events=EventBus(),
        lifecycle=Lifecycle(),
        cancellation=token,
        settings=RuntimeSettings(0.0),
        clock=lambda: 1.0,
    )

    assert bot.run(max_frames=1) == 1
    assert seen == [token]


def test_legacy_pipeline_honors_cancellation_before_native_vision_work() -> None:
    token = CancellationToken()
    token.cancel()
    pipeline = VisionPipeline.__new__(VisionPipeline)
    pipeline.screen_classifier = type("Classifier", (), {"classify": lambda self, image: pytest.fail("must not classify")})()

    with pytest.raises(Exception, match="cancelled"):
        pipeline.analyze(np.zeros((2, 2, 3), dtype=np.uint8), cancellation=token)


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), SystemExit(9)])
def test_control_baseexception_during_stopping_never_skips_capture_stop(failure) -> None:
    class StoppingSink(EventBus):
        def publish(self, event):
            if event.kind is EventKind.LIFECYCLE and event.payload["status"] == "stopping":
                raise failure
            super().publish(event)

    source = Source()
    bot = runtime(source, clock=lambda: 1.0, events=StoppingSink())
    with pytest.raises(type(failure)):
        bot.run(max_frames=1)
    assert source.stopped


def test_freeze_rejects_scalar_subclasses_and_normalizes_real_timestamp() -> None:
    class MutableString(str):
        pass

    class CustomReal(float):
        pass

    with pytest.raises(TypeError):
        RuntimeEvent(EventKind.FRAME, 1.0, {MutableString("key"): "value"})
    with pytest.raises(TypeError):
        RuntimeEvent(EventKind.FRAME, 1.0, {"value": CustomReal(1.0)})
    event = RuntimeEvent(EventKind.FRAME, CustomReal(1.0), {"value": 1})
    assert type(event.emitted_at_monotonic) is float


def test_event_bus_reset_clears_session_state() -> None:
    bus = EventBus(capacity=1)
    bus.publish(RuntimeEvent(EventKind.LIFECYCLE, 1.0, {"status": "running"}))
    bus.publish(RuntimeEvent(EventKind.ERROR, 2.0, {"phase": "run", "error": "x"}))
    bus.reset()
    assert bus.drain() == []
    assert bus.dropped_count == 0
    assert bus.latest_lifecycle is None
    assert bus.latest_error is None


def test_runtime_supports_positional_only_legacy_perception() -> None:
    seen = []

    class Legacy:
        def analyze(self, image, cancellation=None, /):
            seen.append(cancellation)
            return {"screen": "UNKNOWN"}

    bot = runtime(Source(), clock=lambda: 1.0)
    bot._perception = Legacy()
    assert bot.run(max_frames=1) == 1
    assert seen == [None]
