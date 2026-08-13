from __future__ import annotations

import time
from collections.abc import Callable

import cv2
import numpy as np
from loguru import logger

from src.capture.models import CaptureBackend, CapturedImage
from src.device.session import DeviceSession


class ADBCaptureSource:
    def __init__(
        self,
        session: DeviceSession,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_capture_attempts: int = 8,
        retry_delay_seconds: float = 0.08,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if max_capture_attempts <= 0:
            raise ValueError("max_capture_attempts must be positive")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")
        self._session = session
        self._clock = clock
        self._max_capture_attempts = max_capture_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper
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

        for attempt in range(1, self._max_capture_attempts + 1):
            captured_at_monotonic = self._clock()
            rgb = np.asarray(self._session.screencap_png())
            if rgb.ndim != 3 or rgb.shape[2] not in (3, 4):
                raise ValueError(f"unexpected screenshot shape: {rgb.shape!r}")

            visible_rgb = rgb[:, :, :3]
            if not self._is_blank_capture(visible_rgb):
                conversion = (
                    cv2.COLOR_RGBA2BGR
                    if rgb.shape[2] == 4
                    else cv2.COLOR_RGB2BGR
                )
                bgr = cv2.cvtColor(rgb, conversion)
                return CapturedImage(
                    bgr,
                    captured_at_monotonic,
                    CaptureBackend.ADB_PNG,
                )

            logger.warning(
                "ADB returned a blank frame ({}/{}); retrying capture",
                attempt,
                self._max_capture_attempts,
            )
            if attempt < self._max_capture_attempts:
                self._sleeper(self._retry_delay_seconds)

        raise RuntimeError(
            f"ADB returned {self._max_capture_attempts} consecutive blank frames"
        )

    @staticmethod
    def _is_blank_capture(rgb: np.ndarray) -> bool:
        # MEmu can intermittently return a valid all-black PNG from screencap.
        # Such a frame contains no usable visual information and must never be
        # forwarded to perception as a real game state.
        return bool(rgb.max() <= 8 and rgb.std() <= 0.25)

    def stop(self) -> None:
        self._started = False
