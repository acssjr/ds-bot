from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from numbers import Real

import numpy as np

from src.geometry.models import Size


def _require_non_negative_integer(name: str, value: object, *, positive: bool = False) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    minimum = 1 if positive else 0
    if value < minimum:
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must be {qualifier}")


def _require_non_negative_finite_real(name: str, value: object) -> None:
    if not isinstance(value, Real) or isinstance(value, bool):
        raise TypeError(f"{name} must be a real number")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _immutable_bgr_image(image: object) -> np.ndarray:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a NumPy array")
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must be an HxWx3 BGR array")
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise ValueError("image dimensions must be positive")
    if image.dtype != np.uint8:
        raise ValueError("image dtype must be uint8")
    contiguous = np.ascontiguousarray(image)
    immutable = np.frombuffer(contiguous.tobytes(order="C"), dtype=np.uint8).reshape(contiguous.shape)
    immutable.setflags(write=False)
    return immutable


class CaptureBackend(str, Enum):
    ADB_PNG = "adb_png"
    REPLAY = "replay"


class Freshness(str, Enum):
    REUSE_OK = "reuse_ok"
    FRESH_REQUIRED = "fresh_required"


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    freshness: Freshness
    max_age_seconds: float = 0.0
    minimum_generation: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.freshness, Freshness):
            raise TypeError("freshness must be a Freshness")
        _require_non_negative_finite_real("max_age_seconds", self.max_age_seconds)
        _require_non_negative_integer("minimum_generation", self.minimum_generation)

    @classmethod
    def reuse_ok(cls, max_age_seconds: float) -> "CaptureRequest":
        return cls(Freshness.REUSE_OK, max_age_seconds=max_age_seconds)

    @classmethod
    def fresh_required(cls, minimum_generation: int = 0) -> "CaptureRequest":
        return cls(Freshness.FRESH_REQUIRED, minimum_generation=minimum_generation)


@dataclass(frozen=True, slots=True)
class CapturedImage:
    image: np.ndarray = field(repr=False, compare=False)
    captured_at_monotonic: float
    backend: CaptureBackend

    def __post_init__(self) -> None:
        _require_non_negative_finite_real("captured_at_monotonic", self.captured_at_monotonic)
        if not isinstance(self.backend, CaptureBackend):
            raise TypeError("backend must be a CaptureBackend")
        object.__setattr__(self, "image", _immutable_bgr_image(self.image))


@dataclass(frozen=True, slots=True)
class Frame:
    id: int
    image: np.ndarray = field(repr=False, compare=False)
    captured_at_monotonic: float
    device_serial: str
    backend: CaptureBackend
    size: Size
    connection_generation: int
    capture_generation: int

    def __post_init__(self) -> None:
        _require_non_negative_integer("id", self.id, positive=True)
        _require_non_negative_finite_real("captured_at_monotonic", self.captured_at_monotonic)
        if not isinstance(self.device_serial, str):
            raise TypeError("device_serial must be a string")
        device_serial = self.device_serial.strip()
        if not device_serial:
            raise ValueError("device_serial must not be empty")
        object.__setattr__(self, "device_serial", device_serial)
        if not isinstance(self.backend, CaptureBackend):
            raise TypeError("backend must be a CaptureBackend")
        if not isinstance(self.size, Size):
            raise TypeError("size must be a Size")
        _require_non_negative_integer("connection_generation", self.connection_generation)
        _require_non_negative_integer("capture_generation", self.capture_generation)
        image = _immutable_bgr_image(self.image)
        height, width = image.shape[:2]
        if Size(width, height) != self.size:
            raise ValueError("size must match image dimensions")
        object.__setattr__(self, "image", image)

    @classmethod
    def from_capture(
        cls,
        captured: CapturedImage,
        *,
        frame_id: int,
        device_serial: str,
        connection_generation: int,
        capture_generation: int,
    ) -> "Frame":
        height, width = captured.image.shape[:2]
        return cls(
            id=frame_id,
            image=captured.image,
            captured_at_monotonic=captured.captured_at_monotonic,
            device_serial=device_serial,
            backend=captured.backend,
            size=Size(width, height),
            connection_generation=connection_generation,
            capture_generation=capture_generation,
        )

    def age_seconds(self, now_monotonic: float) -> float:
        _require_non_negative_finite_real("now_monotonic", now_monotonic)
        if now_monotonic < self.captured_at_monotonic:
            raise ValueError("now_monotonic must not precede capture time")
        return now_monotonic - self.captured_at_monotonic
