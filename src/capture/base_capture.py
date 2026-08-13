from abc import ABC, abstractmethod
from typing import Optional, Protocol

import numpy as np

from src.capture.models import CapturedImage


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
