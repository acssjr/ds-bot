from __future__ import annotations

import math
import threading
from numbers import Real


class Cancelled(RuntimeError):
    pass


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise Cancelled("operation cancelled")

    def wait(self, timeout_seconds: float) -> None:
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, Real):
            raise TypeError("timeout must be a real number")
        if not math.isfinite(timeout_seconds):
            raise ValueError("timeout must be finite")
        if timeout_seconds < 0:
            raise ValueError("timeout must be non-negative")
        if self._event.wait(timeout_seconds):
            raise Cancelled("operation cancelled")
