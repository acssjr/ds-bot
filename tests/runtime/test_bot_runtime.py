import math
from pathlib import Path

import numpy as np
import pytest

from src.capture.manager import CaptureManager
from src.capture.base_capture import CaptureTemporarilyUnavailable
from src.capture.models import CaptureBackend, CapturedImage
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind
from src.core.lifecycle import Lifecycle, RuntimeStatus
from src.main import build_parser
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.state.game_state import ScreenState
from src.vision.classifiers.screen_classifier import ScreenClassifier
from src.vision.legacy_adapter import LegacyVisionAdapter
from src.vision.pipeline import VisionPipeline


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


def build_runtime(source, perception, *, events=None, settings=None, cancellation=None):
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
        cancellation=cancellation or CancellationToken(),
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


def test_transient_capture_failure_does_not_stop_runtime() -> None:
    class RecoveringSource(OneFrameSource):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def capture(self) -> CapturedImage:
            self.calls += 1
            if self.calls == 1:
                raise CaptureTemporarilyUnavailable(
                    "temporary black frame", attempts=3, blank_frames=3
                )
            return super().capture()

    source = RecoveringSource()
    runtime, events, lifecycle = build_runtime(
        source,
        FakePerception(),
        settings=RuntimeSettings(0.0, capture_retry_seconds=0.0),
    )

    assert runtime.run(max_frames=1) == 1
    assert lifecycle.status is RuntimeStatus.STOPPED
    capture_events = [event for event in events.drain() if event.kind is EventKind.CAPTURE]
    assert [event.payload["status"] for event in capture_events] == ["degraded", "recovered"]


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


@pytest.mark.parametrize("legacy_screen", [None, "not-a-screen", 4])
def test_legacy_adapter_normalizes_invalid_screen_to_unknown(legacy_screen) -> None:
    adapter = LegacyVisionAdapter.__new__(LegacyVisionAdapter)
    adapter._pipeline = type("Pipeline", (), {"analyze": lambda self, image: {"screen": legacy_screen}})()
    assert adapter.analyze(np.zeros((1, 1, 3), dtype=np.uint8))["screen"] == "UNKNOWN"


def test_legacy_adapter_fails_early_for_missing_templates() -> None:
    with pytest.raises(FileNotFoundError, match="templates"):
        LegacyVisionAdapter("does-not-exist")


def test_screen_classifier_does_not_create_missing_templates_directory(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-templates"

    with pytest.raises(FileNotFoundError, match="templates"):
        ScreenClassifier(str(missing))

    assert not missing.exists()


def test_legacy_adapter_supports_explicit_relative_templates_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    templates = tmp_path / "custom-templates"
    templates.mkdir()
    monkeypatch.chdir(tmp_path)

    adapter = LegacyVisionAdapter("custom-templates")

    assert Path(adapter._pipeline.screen_classifier.templates_dir) == templates.resolve()


def test_legacy_pipeline_does_not_fabricate_card_choices() -> None:
    pipeline = VisionPipeline.__new__(VisionPipeline)
    pipeline.screen_classifier = type(
        "Classifier", (), {"classify": lambda self, image: (ScreenState.UNKNOWN, 0.0, None)}
    )()
    pipeline.context_analyzer = type(
        "Context", (), {"analyze": lambda self, image, screen, sub_element: {}}
    )()
    pipeline._last_screen = ScreenState.UNKNOWN
    pipeline._last_confidence = 0.0
    pipeline._unknown_streak = 0

    result = pipeline.analyze(np.zeros((2, 3, 3), dtype=np.uint8))

    assert "available_choices" not in result


def test_cli_requires_exactly_one_capture_source() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--device", "A", "--replay", "screenshots"])
    assert parser.parse_args(["--device", "A"]).device == "A"


def test_runtime_is_single_use() -> None:
    runtime, _, _ = build_runtime(OneFrameSource(), FakePerception())
    assert runtime.run(max_frames=1) == 1
    with pytest.raises(RuntimeError, match="single-use"):
        runtime.run(max_frames=1)


def test_pre_cancelled_runtime_does_not_start_capture_or_lifecycle() -> None:
    token = CancellationToken()
    token.cancel()
    source = OneFrameSource()
    runtime, events, lifecycle = build_runtime(source, FakePerception(), cancellation=token)

    assert runtime.run(max_frames=1) == 0
    assert not source.started and not source.stopped
    assert lifecycle.status is RuntimeStatus.STOPPED
    assert events.drain() == []


def test_runtime_does_not_start_capture_when_cancelled_after_starting_event() -> None:
    token = CancellationToken()

    class CancellingSink(EventBus):
        def publish(self, event) -> None:
            super().publish(event)
            if event.kind is EventKind.LIFECYCLE and event.payload["status"] == "starting":
                token.cancel()

    source = OneFrameSource()
    runtime, events, lifecycle = build_runtime(source, FakePerception(), events=CancellingSink(), cancellation=token)

    assert runtime.run(max_frames=1) == 0
    assert not source.started and not source.stopped
    assert lifecycle.status is RuntimeStatus.STOPPED
    assert [event.payload["status"] for event in events.drain()] == ["starting", "stopping", "stopped"]


def test_runtime_stops_after_cancellation_observed_between_capture_and_analyze() -> None:
    token = CancellationToken()

    class CancellingSource(OneFrameSource):
        def capture(self) -> CapturedImage:
            token.cancel()
            return super().capture()

    source = CancellingSource()
    runtime, events, lifecycle = build_runtime(source, FakePerception(), cancellation=token)

    assert runtime.run(max_frames=1) == 0
    assert source.stopped
    assert lifecycle.status is RuntimeStatus.STOPPED
    assert [event.kind for event in events.drain()] == [
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
    ]


def test_runtime_stops_after_cancellation_observed_between_analyze_and_observation() -> None:
    token = CancellationToken()

    class CancellingPerception:
        def analyze(self, image):
            token.cancel()
            return {"screen": "UNKNOWN"}

    runtime, events, lifecycle = build_runtime(OneFrameSource(), CancellingPerception(), cancellation=token)

    assert runtime.run(max_frames=1) == 0
    assert lifecycle.status is RuntimeStatus.STOPPED
    assert [event.kind for event in events.drain()] == [
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
        EventKind.FRAME,
        EventKind.LIFECYCLE,
        EventKind.LIFECYCLE,
    ]


def test_runtime_requires_mapping_perception_result() -> None:
    class PairPerception:
        def analyze(self, image):
            return [("screen", "UNKNOWN")]

    runtime, _, lifecycle = build_runtime(OneFrameSource(), PairPerception())
    with pytest.raises(TypeError, match="Mapping"):
        runtime.run(max_frames=1)
    assert lifecycle.status is RuntimeStatus.FAILED


def test_runtime_requires_string_observation_keys() -> None:
    class InvalidKeyPerception:
        def analyze(self, image):
            return {1: "UNKNOWN"}

    runtime, _, lifecycle = build_runtime(OneFrameSource(), InvalidKeyPerception())
    with pytest.raises(TypeError, match="strings"):
        runtime.run(max_frames=1)
    assert lifecycle.status is RuntimeStatus.FAILED


def test_sink_failure_does_not_override_authoritative_lifecycle_state() -> None:
    class FailingSink:
        def publish(self, event) -> None:
            raise RuntimeError("sink unavailable")

    runtime, _, lifecycle = build_runtime(OneFrameSource(), FakePerception(), events=FailingSink())
    assert runtime.run(max_frames=1) == 1
    assert lifecycle.status is RuntimeStatus.STOPPED
