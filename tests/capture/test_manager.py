from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from src.capture.adb_source import ADBCaptureSource
from src.capture.base_capture import CaptureTemporarilyUnavailable
from src.capture.manager import CaptureManager
from src.capture.models import CaptureBackend, CaptureRequest, CapturedImage, Frame
from src.capture.replay import ReplayCaptureSource, ReplayExhausted


class FakeClock:
    def __init__(self, value: float = 10.0):
        self.value = value

    def __call__(self) -> float:
        return self.value


class FakeSource:
    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.calls = 0
        self.successful_captures = 0
        self.fail_next: Exception | None = None
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def capture(self) -> CapturedImage:
        self.calls += 1
        if self.fail_next is not None:
            error = self.fail_next
            self.fail_next = None
            raise error
        self.successful_captures += 1
        image = np.full((4, 5, 3), self.successful_captures, dtype=np.uint8)
        return CapturedImage(image, self.clock(), CaptureBackend.REPLAY)

    def stop(self) -> None:
        self.stopped = True


class FakeSession:
    def __init__(self, image: np.ndarray | None = None, *, on_screenshot=None):
        self.connected = False
        self.connection_generation = 0
        self.connect_calls = 0
        self.screenshot_error_ok: list[bool] = []
        self.image = image if image is not None else np.array(
            [[[255, 0, 0], [0, 255, 0]]], dtype=np.uint8
        )
        self.on_screenshot = on_screenshot

    def connect(self) -> None:
        self.connected = True
        self.connection_generation += 1
        self.connect_calls += 1

    def screenshot(self, *, error_ok: bool = False):
        self.screenshot_error_ok.append(error_ok)
        if self.on_screenshot is not None:
            self.on_screenshot()
        return Image.fromarray(self.image)

    def screencap_png(self):
        return self.screenshot(error_ok=False)


def test_adb_source_requires_active_lifecycle_and_converts_rgb_to_bgr() -> None:
    session = FakeSession()
    source = ADBCaptureSource(session, clock=lambda: 3.0)
    with pytest.raises(RuntimeError, match="not started"):
        source.capture()
    source.start()
    source.start()
    captured = source.capture()
    source.stop()

    assert session.connected
    assert session.connect_calls == 1
    assert session.screenshot_error_ok == [False]
    assert captured.backend is CaptureBackend.ADB_PNG
    assert captured.captured_at_monotonic == 3.0
    assert captured.image.tolist() == [[[0, 0, 255], [0, 255, 0]]]
    with pytest.raises(RuntimeError, match="not started"):
        source.capture()


def test_adb_source_uses_only_dedicated_observe_only_screencap() -> None:
    class ObserveOnlySession:
        connected = False
        connection_generation = 0

        def connect(self) -> None:
            self.connected = True
            self.connection_generation += 1

        def screencap_png(self):
            return Image.fromarray(np.array([[[255, 0, 0]]], dtype=np.uint8))

        def __getattr__(self, name):
            if name in {"click", "swipe", "shell", "stop_app", "start_app"}:
                raise AssertionError(f"unsafe operation requested: {name}")
            raise AttributeError(name)

    source = ADBCaptureSource(ObserveOnlySession(), clock=lambda: 3.0)
    source.start()
    captured = source.capture()

    assert captured.image.tolist() == [[[0, 0, 255]]]


def test_adb_source_samples_timestamp_before_screenshot() -> None:
    clock = FakeClock(2.0)
    session = FakeSession(on_screenshot=lambda: setattr(clock, "value", 3.0))
    source = ADBCaptureSource(session, clock=clock)
    source.start()

    captured = source.capture()

    assert captured.captured_at_monotonic == 2.0


def test_adb_source_converts_rgba_to_bgr() -> None:
    rgba = np.array([[[1, 2, 3, 4]]], dtype=np.uint8)
    source = ADBCaptureSource(FakeSession(rgba), clock=lambda: 3.0)
    source.start()

    captured = source.capture()

    assert captured.image.tolist() == [[[3, 2, 1]]]


def test_adb_source_rejects_grayscale_screenshot() -> None:
    grayscale = np.array([[0, 255]], dtype=np.uint8)
    source = ADBCaptureSource(FakeSession(grayscale), clock=lambda: 3.0)
    source.start()

    with pytest.raises(ValueError, match="unexpected screenshot shape"):
        source.capture()


def test_adb_source_retries_intermittent_blank_memu_frames() -> None:
    class IntermittentSession:
        connected = True
        connection_generation = 1

        def __init__(self) -> None:
            self.calls = 0

        def screencap_png(self):
            self.calls += 1
            if self.calls < 3:
                return Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8))
            return Image.fromarray(
                np.array([[[255, 0, 0], [0, 255, 0]]], dtype=np.uint8)
            )

    session = IntermittentSession()
    delays: list[float] = []
    source = ADBCaptureSource(
        session,
        clock=lambda: 3.0,
        max_capture_attempts=3,
        retry_delay_seconds=0.01,
        sleeper=delays.append,
    )
    source.start()

    captured = source.capture()

    assert session.calls == 3
    assert delays == [0.01, 0.01]
    assert captured.image.max() == 255


def test_adb_source_rejects_consecutive_blank_memu_frames() -> None:
    source = ADBCaptureSource(
        FakeSession(np.zeros((2, 2, 3), dtype=np.uint8)),
        clock=lambda: 3.0,
        max_capture_attempts=2,
        retry_delay_seconds=0,
        sleeper=lambda _delay: None,
    )
    source.start()

    with pytest.raises(CaptureTemporarilyUnavailable, match="4 consecutive blank frames"):
        source.capture()


def test_adb_source_rejects_nearly_black_memu_frame_with_pixel_sparkles() -> None:
    almost_black = np.zeros((200, 200, 3), dtype=np.uint8)
    almost_black[0, 0] = (255, 180, 20)
    source = ADBCaptureSource(
        FakeSession(almost_black),
        clock=lambda: 3.0,
        max_capture_attempts=1,
        retry_delay_seconds=0,
    )
    source.start()

    with pytest.raises(CaptureTemporarilyUnavailable):
        source.capture()


def test_adb_source_uses_adbutils_as_independent_third_strategy() -> None:
    class ThreeStrategySession:
        connected = True
        connection_generation = 1

        def screencap_exec_out_png(self):
            return Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8))

        def screencap_png(self):
            return Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8))

        def screenshot(self):
            return Image.fromarray(np.full((2, 2, 3), 127, dtype=np.uint8))

    source = ADBCaptureSource(ThreeStrategySession(), clock=lambda: 3.0)
    source.start()

    captured = source.capture()

    assert captured.image.mean() == 127
    assert source.health.last_strategy == "adbutils"


def test_adb_source_refreshes_handle_after_repeated_unavailable_cycles() -> None:
    class ResettableBlankSession:
        connected = True
        connection_generation = 1

        def __init__(self) -> None:
            self.reconnect_calls = 0

        def screencap_png(self):
            return Image.fromarray(np.zeros((2, 2, 3), dtype=np.uint8))

        def reconnect(self):
            self.reconnect_calls += 1

    session = ResettableBlankSession()
    source = ADBCaptureSource(
        session,
        max_capture_attempts=1,
        retry_delay_seconds=0,
        reset_after_failures=3,
    )
    source.start()

    for _ in range(3):
        with pytest.raises(CaptureTemporarilyUnavailable):
            source.capture()

    assert session.reconnect_calls == 1
    assert source.health.connection_resets == 1
    assert source.health.consecutive_failures == 3


def test_manager_reuses_only_a_fresh_frame_from_current_generation() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)
    manager.start()

    first = manager.next_frame(CaptureRequest.fresh_required())
    reused = manager.next_frame(CaptureRequest.reuse_ok(0.5))
    assert reused is first
    assert source.calls == 1

    clock.value += 0.6
    expired = manager.next_frame(CaptureRequest.reuse_ok(0.5))
    assert expired.id == 2
    assert source.calls == 2


def test_manager_reuses_a_frame_at_exactly_max_age() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)
    manager.start()
    first = manager.next_frame(CaptureRequest.fresh_required())

    clock.value += 0.5

    assert manager.next_frame(CaptureRequest.reuse_ok(0.5)) is first
    assert source.calls == 1


def test_connection_generation_change_invalidates_cached_frame() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    generation = [1]
    manager = CaptureManager(
        source,
        device_serial="replay",
        connection_generation=lambda: generation[0],
        clock=clock,
    )
    manager.start()
    first = manager.next_frame(CaptureRequest.fresh_required())
    generation[0] = 2
    second = manager.next_frame(CaptureRequest.reuse_ok(10.0))

    assert second is not first
    assert second.id == 2
    assert second.connection_generation == 2
    assert source.calls == 2


def test_input_invalidation_forces_a_new_generation_and_frame() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)
    manager.start()
    first = manager.next_frame(CaptureRequest.fresh_required())

    generation = manager.invalidate_after_input()
    second = manager.next_frame(CaptureRequest.fresh_required(generation))

    assert second.id == first.id + 1
    assert second.capture_generation == generation
    assert source.calls == 2


def test_manager_requires_active_lifecycle_and_drops_cache_on_restart() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)
    with pytest.raises(RuntimeError, match="not started"):
        manager.next_frame(CaptureRequest.fresh_required())
    manager.start()
    first = manager.next_frame(CaptureRequest.fresh_required())
    manager.stop()
    with pytest.raises(RuntimeError, match="not started"):
        manager.next_frame(CaptureRequest.reuse_ok(10.0))
    manager.start()
    second = manager.next_frame(CaptureRequest.reuse_ok(10.0))
    assert second is not first
    assert second.id == first.id + 1


def test_failed_capture_preserves_cache_and_next_frame_id() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)
    manager.start()
    first = manager.next_frame(CaptureRequest.fresh_required())
    source.fail_next = RuntimeError("capture failure")

    with pytest.raises(RuntimeError, match="capture failure"):
        manager.next_frame(CaptureRequest.fresh_required())

    assert manager.next_frame(CaptureRequest.reuse_ok(10.0)) is first
    second = manager.next_frame(CaptureRequest.fresh_required())
    assert second.id == first.id + 1
    assert source.calls == 3


def test_replay_reads_each_file_once_and_reports_exhaustion(tmp_path: Path) -> None:
    paths = []
    for index in range(2):
        path = tmp_path / f"{index}.png"
        assert cv2.imwrite(str(path), np.full((3, 4, 3), index, dtype=np.uint8))
        paths.append(path)

    replay = ReplayCaptureSource(paths, clock=lambda: 5.0)
    with pytest.raises(RuntimeError, match="not started"):
        replay.capture()
    replay.start()
    first = replay.capture()
    replay.start()
    assert int(first.image[0, 0, 0]) == 0
    assert int(replay.capture().image[0, 0, 0]) == 1
    with pytest.raises(ReplayExhausted):
        replay.capture()
    replay.stop()
    with pytest.raises(RuntimeError, match="not started"):
        replay.capture()


def test_replay_decode_failure_does_not_consume_path(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.png"
    invalid.write_bytes(b"not a png")
    valid = tmp_path / "valid.png"
    assert cv2.imwrite(str(valid), np.full((3, 4, 3), 2, dtype=np.uint8))
    replay = ReplayCaptureSource([invalid, valid], clock=lambda: 5.0)
    replay.start()

    with pytest.raises(ValueError, match="unable to decode replay image"):
        replay.capture()

    assert cv2.imwrite(str(invalid), np.full((3, 4, 3), 1, dtype=np.uint8))
    assert int(replay.capture().image[0, 0, 0]) == 1
    assert int(replay.capture().image[0, 0, 0]) == 2


def test_manager_rolls_back_partial_start_without_masking_primary_error() -> None:
    class PartiallyStartedSource:
        def __init__(self):
            self.started = False
            self.stopped = False
            self.stop_calls = 0

        def start(self) -> None:
            self.started = True
            raise RuntimeError("start failed")

        def capture(self) -> CapturedImage:
            raise AssertionError("capture must not run")

        def stop(self) -> None:
            self.stop_calls += 1
            self.stopped = True
            raise RuntimeError("rollback failed")

    source = PartiallyStartedSource()
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 0)

    with pytest.raises(RuntimeError, match="start failed") as caught:
        manager.start()

    assert source.stop_calls == 1
    assert source.started and source.stopped
    assert any("rollback also failed" in note for note in caught.value.__notes__)
    with pytest.raises(RuntimeError, match="not started"):
        manager.next_frame(CaptureRequest.fresh_required())


def test_manager_rolls_back_partial_start_for_keyboard_interrupt() -> None:
    class InterruptedSource:
        def __init__(self):
            self.stopped = False

        def start(self) -> None:
            raise KeyboardInterrupt("interrupted")

        def capture(self) -> CapturedImage:
            raise AssertionError("capture must not run")

        def stop(self) -> None:
            self.stopped = True

    source = InterruptedSource()
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 0)
    with pytest.raises(KeyboardInterrupt, match="interrupted"):
        manager.start()
    assert source.stopped


def test_frame_reuses_captured_image_buffer_while_preserving_immutability() -> None:
    image = np.zeros((2, 3, 3), dtype=np.uint8)
    captured = CapturedImage(image, 1.0, CaptureBackend.REPLAY)
    frame = Frame.from_capture(
        captured,
        frame_id=1,
        device_serial="replay",
        connection_generation=0,
        capture_generation=0,
    )

    assert frame.image is captured.image
    assert not frame.image.flags.writeable
    with pytest.raises(ValueError):
        frame.image[0, 0, 0] = 1
