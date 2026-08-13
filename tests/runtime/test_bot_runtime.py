import math

import numpy as np
import pytest

from src.capture.manager import CaptureManager
from src.capture.models import CaptureBackend, CapturedImage
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind
from src.core.lifecycle import Lifecycle, RuntimeStatus
from src.main import build_parser
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.state.game_state import ScreenState
from src.vision.legacy_adapter import LegacyVisionAdapter


class OneFrameSource:
    def __init__(self, *, stop_error: Exception | None = None):
        self.started = False
        self.stopped = False
        self.stop_error = stop_error

    def start(self) -> None:
        self.started = True

    def capture(self) -> CapturedImage:
        return CapturedImage(np.zeros((4, 5, 3), dtype=np.uint8), 1.0, CaptureBackend.REPLAY)

    def stop(self) -> None:
        self.stopped = True
        if self.stop_error is not None:
            raise self.stop_error


class FakePerception:
    def analyze(self, image):
        return {"screen": "UNKNOWN", "confidence": 0.0, "shape": image.shape}


class FailingPerception:
    def analyze(self, image):
        raise RuntimeError("vision failed")


def build_runtime(source, perception, *, events=None, settings=None):
    manager = CaptureManager(
        source,
        device_serial="replay",
        connection_generation=lambda: 0,
        clock=lambda: 1.0,
    )
    event_bus = events or EventBus()
    lifecycle = Lifecycle()
    runtime = BotRuntime(
        capture=manager,
        perception=perception,
        events=event_bus,
        lifecycle=lifecycle,
        cancellation=CancellationToken(),
        settings=settings or RuntimeSettings(poll_interval_seconds=0.0),
        clock=lambda: 1.0,
    )
    return runtime, event_bus, lifecycle


def test_runtime_processes_one_frame_and_has_no_input_dependency() -> None:
    source = OneFrameSource()
    runtime, events, lifecycle = build_runtime(source, FakePerception())

    assert runtime.run(max_frames=1) == 1
    assert source.started and source.stopped
    assert lifecycle.status is RuntimeStatus.STOPPED
    drained = events.drain()
    kinds = [event.kind for event in drained]
    assert kinds == [
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
        EventKind.FRAME,
        EventKind.OBSERVATION,
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
    ]
    assert EventKind.INPUT not in kinds
    assert drained[2].payload["frame_id"] == 1
    assert drained[3].payload["frame_id"] == 1


def test_runtime_stops_capture_and_preserves_failed_status() -> None:
    source = OneFrameSource()
    runtime, events, lifecycle = build_runtime(source, FailingPerception())

    with pytest.raises(RuntimeError, match="vision failed"):
        runtime.run(max_frames=1)
    assert source.stopped
    assert lifecycle.status is RuntimeStatus.FAILED
    assert EventKind.ERROR in [event.kind for event in events.drain()]


def test_cleanup_failure_is_reported_as_runtime_failure() -> None:
    source = OneFrameSource(stop_error=RuntimeError("stop failed"))
    runtime, events, lifecycle = build_runtime(source, FakePerception())

    with pytest.raises(RuntimeError, match="stop failed"):
        runtime.run(max_frames=1)
    assert lifecycle.status is RuntimeStatus.FAILED
    drained = events.drain()
    assert any(event.kind is EventKind.ERROR and "stop failed" in event.payload["error"] for event in drained)


def test_cleanup_failure_does_not_mask_primary_failure() -> None:
    source = OneFrameSource(stop_error=RuntimeError("stop failed"))
    runtime, events, lifecycle = build_runtime(source, FailingPerception())

    with pytest.raises(RuntimeError, match="vision failed") as caught:
        runtime.run(max_frames=1)
    assert any("cleanup also failed" in note for note in getattr(caught.value, "__notes__", []))
    assert lifecycle.status is RuntimeStatus.FAILED
    assert EventKind.ERROR in [event.kind for event in events.drain()]


@pytest.mark.parametrize("interval", [True, -1.0, math.nan, math.inf, object()])
def test_runtime_settings_reject_invalid_poll_interval(interval) -> None:
    with pytest.raises((TypeError, ValueError), match="poll interval"):
        RuntimeSettings(poll_interval_seconds=interval)


class FakeLegacyPipeline:
    def analyze(self, image):
        return {
            "screen": ScreenState.UNKNOWN,
            "confidence": 0.0,
            "sub_element": None,
            "available_choices": ["fabricated"],
            "frame_shape": image.shape,
        }


def test_legacy_adapter_removes_fabricated_choices_and_numpy_shape() -> None:
    adapter = LegacyVisionAdapter.__new__(LegacyVisionAdapter)
    adapter._pipeline = FakeLegacyPipeline()
    result = adapter.analyze(np.zeros((2, 3, 3), dtype=np.uint8))
    assert result == {"screen": "UNKNOWN", "confidence": 0.0, "sub_element": None}


def test_cli_requires_exactly_one_capture_source() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--device", "A", "--replay", "screenshots"])
    assert parser.parse_args(["--device", "A"]).device == "A"
