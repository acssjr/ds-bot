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

    def start(self) -> None:
        self._index = 0

    def capture(self) -> CapturedImage:
        if self._index >= len(self._paths):
            raise ReplayExhausted("replay sequence is complete")
        path = self._paths[self._index]
        self._index += 1
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"unable to decode replay image: {path}")
        return CapturedImage(image, self._clock(), CaptureBackend.REPLAY)

    def stop(self) -> None:
        pass
