from __future__ import annotations

import time
from collections.abc import Callable

import cv2
import numpy as np

from src.capture.models import CaptureBackend, CapturedImage
from src.device.session import DeviceSession


class ADBCaptureSource:
    def __init__(self, session: DeviceSession, *, clock: Callable[[], float] = time.monotonic):
        self._session = session
        self._clock = clock
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        if not self._session.connected:
            self._session.connect()
        self._started = True

    def capture(self) -> CapturedImage:
        if not self._started:
            raise RuntimeError("ADB capture source is not started")
        captured_at_monotonic = self._clock()
        rgb = np.asarray(self._session.screencap_png())
        if rgb.ndim != 3 or rgb.shape[2] not in (3, 4):
            raise ValueError(f"unexpected screenshot shape: {rgb.shape!r}")
        conversion = cv2.COLOR_RGBA2BGR if rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR
        bgr = cv2.cvtColor(rgb, conversion)
        return CapturedImage(bgr, captured_at_monotonic, CaptureBackend.ADB_PNG)

    def stop(self) -> None:
        self._started = False
