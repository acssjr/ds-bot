from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.geometry.models import PixelPoint


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
        if not self.command_id:
            raise ValueError("command id is required")
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
