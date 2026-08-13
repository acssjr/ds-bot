from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.capture.models import CaptureBackend, CaptureRequest, CapturedImage
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
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def capture(self) -> CapturedImage:
        self.calls += 1
        image = np.full((4, 5, 3), self.calls, dtype=np.uint8)
        return CapturedImage(image, self.clock(), CaptureBackend.REPLAY)

    def stop(self) -> None:
        self.stopped = True


class FakeSession:
    def __init__(self):
        self.connected = False
        self.connection_generation = 0
        self.connect_calls = 0

    def connect(self) -> None:
        self.connected = True
        self.connection_generation += 1
        self.connect_calls += 1

    def screenshot(self):
        rgb = np.array([[[255, 0, 0], [0, 255, 0]]], dtype=np.uint8)
        return Image.fromarray(rgb, mode="RGB")


def test_adb_source_connects_once_and_converts_rgb_to_bgr() -> None:
    session = FakeSession()
    source = ADBCaptureSource(session, clock=lambda: 3.0)
    source.start()
    source.start()
    captured = source.capture()

    assert session.connected
    assert session.connect_calls == 1
    assert captured.backend is CaptureBackend.ADB_PNG
    assert captured.captured_at_monotonic == 3.0
    assert captured.image.tolist() == [[[0, 0, 255], [0, 255, 0]]]


def test_manager_reuses_only_a_fresh_frame_from_current_generation() -> None:
    clock = FakeClock()
    source = FakeSource(clock)
    manager = CaptureManager(source, device_serial="replay", connection_generation=lambda: 1, clock=clock)

    first = manager.next_frame(CaptureRequest.fresh_required())
    reused = manager.next_frame(CaptureRequest.reuse_ok(0.5))
    assert reused is first
    assert source.calls == 1

    clock.value += 0.6
    expired = manager.next_frame(CaptureRequest.reuse_ok(0.5))
    assert expired.id == 2
    assert source.calls == 2


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
    first = manager.next_frame(CaptureRequest.fresh_required())

    generation = manager.invalidate_after_input()
    second = manager.next_frame(CaptureRequest.fresh_required(generation))

    assert second.id == first.id + 1
    assert second.capture_generation == generation
    assert source.calls == 2


def test_replay_reads_each_file_once_and_reports_exhaustion(tmp_path: Path) -> None:
    paths = []
    for index in range(2):
        path = tmp_path / f"{index}.png"
        assert cv2.imwrite(str(path), np.full((3, 4, 3), index, dtype=np.uint8))
        paths.append(path)

    replay = ReplayCaptureSource(paths, clock=lambda: 5.0)
    replay.start()
    assert int(replay.capture().image[0, 0, 0]) == 0
    assert int(replay.capture().image[0, 0, 0]) == 1
    with pytest.raises(ReplayExhausted):
        replay.capture()
