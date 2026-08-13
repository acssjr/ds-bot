import math

import numpy as np
import pytest

from src.capture.base_capture import BaseCapture, CaptureSource
from src.capture.models import CaptureBackend, CaptureRequest, CapturedImage, Frame, Freshness
from src.geometry.models import Size


def test_frame_owns_a_read_only_image_and_provenance() -> None:
    original = np.zeros((8, 6, 3), dtype=np.uint8)
    captured = CapturedImage(original, 10.0, CaptureBackend.REPLAY)
    frame = Frame.from_capture(
        captured,
        frame_id=7,
        device_serial="replay",
        connection_generation=2,
        capture_generation=3,
    )

    original[0, 0, 0] = 255
    assert frame.id == 7
    assert frame.size == Size(6, 8)
    assert frame.image[0, 0, 0] == 0
    with pytest.raises(ValueError):
        frame.image[0, 0, 0] = 1


def test_capture_requests_validate_age_and_generation() -> None:
    assert CaptureRequest.reuse_ok(0.25).freshness is Freshness.REUSE_OK
    assert CaptureRequest.fresh_required(4).minimum_generation == 4
    with pytest.raises(ValueError):
        CaptureRequest.reuse_ok(-0.1)


def test_captured_image_owns_an_immutable_numeric_buffer() -> None:
    original = np.zeros((2, 3, 3), dtype=np.uint8)
    captured = CapturedImage(original, 1.0, CaptureBackend.REPLAY)
    original[0, 0, 0] = 9
    assert captured.image[0, 0, 0] == 0
    with pytest.raises(ValueError):
        captured.image.setflags(write=True)


def test_frame_writeability_cannot_be_reenabled() -> None:
    captured = CapturedImage(np.zeros((2, 3, 3), dtype=np.uint8), 1.0, CaptureBackend.REPLAY)
    frame = Frame.from_capture(
        captured,
        frame_id=1,
        device_serial="replay",
        connection_generation=0,
        capture_generation=0,
    )
    with pytest.raises(ValueError):
        frame.image.setflags(write=True)


@pytest.mark.parametrize(
    "image",
    [
        None,
        np.empty((0, 3, 3), dtype=np.uint8),
        np.empty((2, 0, 3), dtype=np.uint8),
        np.empty((2, 3, 4), dtype=np.uint8),
        np.empty((2, 3, 3), dtype=object),
        np.empty((2, 3, 3), dtype=np.float32),
    ],
)
def test_captured_image_rejects_unsupported_arrays(image) -> None:
    with pytest.raises((TypeError, ValueError)):
        CapturedImage(image, 1.0, CaptureBackend.REPLAY)


@pytest.mark.parametrize("max_age", [True, -1.0, math.nan, math.inf])
def test_capture_request_rejects_invalid_max_age(max_age) -> None:
    with pytest.raises((TypeError, ValueError)):
        CaptureRequest(Freshness.REUSE_OK, max_age_seconds=max_age)


@pytest.mark.parametrize("generation", [True, -1, 1.5])
def test_capture_request_rejects_invalid_generation(generation) -> None:
    with pytest.raises((TypeError, ValueError)):
        CaptureRequest(Freshness.FRESH_REQUIRED, minimum_generation=generation)


def test_capture_request_requires_freshness_enum() -> None:
    with pytest.raises(TypeError):
        CaptureRequest("reuse_ok")


@pytest.mark.parametrize("timestamp", [True, -1.0, math.nan, math.inf])
def test_captured_image_rejects_invalid_timestamp(timestamp) -> None:
    with pytest.raises((TypeError, ValueError)):
        CapturedImage(np.zeros((2, 3, 3), dtype=np.uint8), timestamp, CaptureBackend.REPLAY)


def test_captured_image_requires_backend_enum() -> None:
    with pytest.raises(TypeError):
        CapturedImage(np.zeros((2, 3, 3), dtype=np.uint8), 1.0, "replay")


def valid_frame_kwargs() -> dict:
    return {
        "id": 1,
        "image": np.zeros((2, 3, 3), dtype=np.uint8),
        "captured_at_monotonic": 1.0,
        "device_serial": "replay",
        "backend": CaptureBackend.REPLAY,
        "size": Size(3, 2),
        "connection_generation": 0,
        "capture_generation": 0,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", True),
        ("id", 0),
        ("id", 1.5),
        ("captured_at_monotonic", math.nan),
        ("device_serial", ""),
        ("device_serial", "   "),
        ("backend", "replay"),
        ("connection_generation", True),
        ("connection_generation", -1),
        ("capture_generation", 1.5),
        ("size", Size(2, 2)),
    ],
)
def test_direct_frame_construction_rejects_invalid_provenance(field, value) -> None:
    kwargs = valid_frame_kwargs()
    kwargs[field] = value
    with pytest.raises((TypeError, ValueError)):
        Frame(**kwargs)


def test_direct_frame_construction_also_freezes_image() -> None:
    frame = Frame(**valid_frame_kwargs())
    with pytest.raises(ValueError):
        frame.image.setflags(write=True)


@pytest.mark.parametrize("now", [True, math.nan, math.inf, 0.5])
def test_frame_age_rejects_invalid_or_regressive_clock(now) -> None:
    frame = Frame(**valid_frame_kwargs())
    with pytest.raises((TypeError, ValueError)):
        frame.age_seconds(now)


class FakeLegacyCapture(BaseCapture):
    def start(self) -> bool:
        return True

    def get_latest_frame(self):
        return None

    def stop(self) -> None:
        pass


def test_legacy_base_capture_remains_usable_during_migration() -> None:
    capture = FakeLegacyCapture()
    assert capture.start() is True
    assert capture.get_latest_frame() is None
    capture.stop()
    assert CaptureSource.__name__ == "CaptureSource"
