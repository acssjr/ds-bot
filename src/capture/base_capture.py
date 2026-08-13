from abc import ABC, abstractmethod
from typing import Optional, Protocol

import numpy as np

from src.capture.models import CapturedImage


class CaptureTemporarilyUnavailable(RuntimeError):
    """No useful frame is available yet, but the capture session remains usable."""

    def __init__(self, message: str, *, attempts: int, blank_frames: int) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.blank_frames = blank_frames


class CaptureSource(Protocol):
    def start(self) -> None: ...

    def capture(self) -> CapturedImage: ...

    def stop(self) -> None: ...


class BaseCapture(ABC):
    """Legacy capture interface retained until runtime migration is complete."""

    @abstractmethod
    def start(self) -> bool:
        """Initialize capture."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Return the latest BGR image."""
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> None:
        """Release capture resources."""
        raise NotImplementedError
