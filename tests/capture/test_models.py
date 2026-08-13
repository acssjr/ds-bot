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


def test_legacy_base_capture_remains_importable_during_migration() -> None:
    assert BaseCapture.__name__ == "BaseCapture"
    assert CaptureSource.__name__ == "CaptureSource"
