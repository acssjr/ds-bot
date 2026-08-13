from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from pathlib import Path

import cv2

from src.capture.models import CaptureBackend, CapturedImage


class ReplayExhausted(EOFError):
    pass


class ReplayCaptureSource:
    def __init__(
        self,
        paths: Iterable[Path],
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._paths = tuple(Path(path) for path in paths)
        if not self._paths:
            raise ValueError("replay requires at least one image")
        self._clock = clock
        self._index = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._index = 0
        self._started = True

    def capture(self) -> CapturedImage:
        if not self._started:
            raise RuntimeError("replay capture source is not started")
        if self._index >= len(self._paths):
            raise ReplayExhausted("replay sequence is complete")
        path = self._paths[self._index]
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"unable to decode replay image: {path}")
        captured = CapturedImage(image, self._clock(), CaptureBackend.REPLAY)
        self._index += 1
        return captured

    def stop(self) -> None:
        self._started = False
