from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from src.geometry.models import Size


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
        if self.max_age_seconds < 0:
            raise ValueError("max age must be non-negative")
        if self.minimum_generation < 0:
            raise ValueError("minimum generation must be non-negative")

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
        if self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError("captured image must be an HxWx3 BGR array")


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
        image = np.ascontiguousarray(captured.image).copy()
        image.setflags(write=False)
        height, width = image.shape[:2]
        return cls(
            id=frame_id,
            image=image,
            captured_at_monotonic=captured.captured_at_monotonic,
            device_serial=device_serial,
            backend=captured.backend,
            size=Size(width, height),
            connection_generation=connection_generation,
            capture_generation=capture_generation,
        )

    def age_seconds(self, now_monotonic: float) -> float:
        return max(0.0, now_monotonic - self.captured_at_monotonic)
