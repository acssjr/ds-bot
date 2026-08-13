from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from numbers import Real

from src.geometry.models import PixelPoint


def _require_non_empty_text(name: str, value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} is required")
    return normalized


def _require_timestamp(name: str, value: object) -> None:
    if not isinstance(value, Real) or isinstance(value, bool):
        raise TypeError(f"{name} must be a real number")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


class InputStatus(str, Enum):
    DRY_RUN = "dry_run"
    FAILED_BEFORE_SEND = "failed_before_send"
    SENT = "sent"
    COMMIT_UNKNOWN = "commit_unknown"


@dataclass(frozen=True, slots=True)
class TapCommand:
    command_id: str
    point: PixelPoint
    hold_ms: int = 30

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "command_id", _require_non_empty_text("command_id", self.command_id)
        )
        if not isinstance(self.point, PixelPoint):
            raise TypeError("point must be a PixelPoint")
        if not isinstance(self.hold_ms, int) or isinstance(self.hold_ms, bool):
            raise TypeError("hold_ms must be an integer")
        if self.hold_ms <= 0:
            raise ValueError("hold duration must be positive")


@dataclass(frozen=True, slots=True)
class InputReceipt:
    command_id: str
    status: InputStatus
    backend: str
    started_at_monotonic: float
    completed_at_monotonic: float
    detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "command_id", _require_non_empty_text("command_id", self.command_id)
        )
        if not isinstance(self.status, InputStatus):
            raise TypeError("status must be an InputStatus")
        object.__setattr__(self, "backend", _require_non_empty_text("backend", self.backend))
        _require_timestamp("started_at_monotonic", self.started_at_monotonic)
        _require_timestamp("completed_at_monotonic", self.completed_at_monotonic)
        if self.completed_at_monotonic < self.started_at_monotonic:
            raise ValueError("completed_at_monotonic must not precede started_at_monotonic")
        if not isinstance(self.detail, str):
            raise TypeError("detail must be a string")
