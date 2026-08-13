from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
from loguru import logger

from src.capture.base_capture import CaptureTemporarilyUnavailable
from src.capture.models import CaptureBackend, CapturedImage
from src.device.session import DeviceSession


@dataclass(frozen=True, slots=True)
class CaptureHealth:
    attempts: int
    valid_frames: int
    blank_frames: int
    operation_errors: int
    transient_failures: int
    recoveries: int
    consecutive_failures: int
    connection_resets: int
    last_strategy: str


class ADBCaptureSource:
    def __init__(
        self,
        session: DeviceSession,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_capture_attempts: int = 3,
        retry_delay_seconds: float = 0.08,
        sleeper: Callable[[float], None] = time.sleep,
        reset_after_failures: int = 3,
    ):
        if max_capture_attempts <= 0:
            raise ValueError("max_capture_attempts must be positive")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")
        if reset_after_failures <= 0:
            raise ValueError("reset_after_failures must be positive")
        self._session = session
        self._clock = clock
        self._max_capture_attempts = max_capture_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper
        self._reset_after_failures = reset_after_failures
        self._started = False
        self._attempts = 0
        self._valid_frames = 0
        self._blank_frames = 0
        self._operation_errors = 0
        self._transient_failures = 0
        self._recoveries = 0
        self._consecutive_failures = 0
        self._connection_resets = 0
        self._last_strategy = "-"
        self._degraded = False

    @property
    def health(self) -> CaptureHealth:
        return CaptureHealth(
            attempts=self._attempts,
            valid_frames=self._valid_frames,
            blank_frames=self._blank_frames,
            operation_errors=self._operation_errors,
            transient_failures=self._transient_failures,
            recoveries=self._recoveries,
            consecutive_failures=self._consecutive_failures,
            connection_resets=self._connection_resets,
            last_strategy=self._last_strategy,
        )

    def start(self) -> None:
        if self._started:
            return
        if not self._session.connected:
            self._session.connect()
        self._started = True

    def capture(self) -> CapturedImage:
        if not self._started:
            raise RuntimeError("ADB capture source is not started")

        blank_in_cycle = 0
        errors_in_cycle = 0
        strategies = []
        exec_out = getattr(self._session, "screencap_exec_out_png", None)
        if callable(exec_out):
            strategies.append(("exec-out", exec_out))
        strategies.append(("shell", self._session.screencap_png))
        adbutils_screenshot = getattr(type(self._session), "screenshot", None)
        if callable(adbutils_screenshot):
            strategies.append(
                ("adbutils", lambda: adbutils_screenshot(self._session))
            )

        for attempt in range(1, self._max_capture_attempts + 1):
            for strategy, capture_image in strategies:
                captured_at_monotonic = self._clock()
                self._attempts += 1
                try:
                    rgb = np.asarray(capture_image())
                except Exception:
                    errors_in_cycle += 1
                    self._operation_errors += 1
                    continue
                if rgb.ndim != 3 or rgb.shape[2] not in (3, 4):
                    raise ValueError(f"unexpected screenshot shape: {rgb.shape!r}")

                visible_rgb = rgb[:, :, :3]
                if not self._is_blank_capture(visible_rgb):
                    conversion = cv2.COLOR_RGBA2BGR if rgb.shape[2] == 4 else cv2.COLOR_RGB2BGR
                    bgr = cv2.cvtColor(rgb, conversion)
                    self._valid_frames += 1
                    self._last_strategy = strategy
                    if self._degraded:
                        self._recoveries += 1
                        logger.info(
                            "ADB capture recovered using {}; {} blank frame(s) skipped",
                            strategy,
                            blank_in_cycle,
                        )
                    self._degraded = False
                    self._consecutive_failures = 0
                    return CapturedImage(bgr, captured_at_monotonic, CaptureBackend.ADB_PNG)

                blank_in_cycle += 1
                self._blank_frames += 1
            if attempt < self._max_capture_attempts:
                self._sleeper(self._retry_delay_seconds)

        self._transient_failures += 1
        self._consecutive_failures += 1
        self._degraded = True
        if self._consecutive_failures % self._reset_after_failures == 0:
            reconnect = getattr(self._session, "reconnect", None)
            if callable(reconnect):
                try:
                    reconnect()
                    self._connection_resets += 1
                    logger.info(
                        "ADB capture handle refreshed after {} consecutive unavailable cycle(s)",
                        self._consecutive_failures,
                    )
                except Exception as exc:
                    self._operation_errors += 1
                    logger.warning("ADB capture handle refresh failed: {!r}", exc)
        if self._consecutive_failures == 1 or self._consecutive_failures % 10 == 0:
            logger.warning(
                "ADB capture temporarily unavailable: {} blank result(s), {} operation error(s); observation remains active (cycle {})",
                blank_in_cycle,
                errors_in_cycle,
                self._consecutive_failures,
            )
        raise CaptureTemporarilyUnavailable(
            f"ADB returned {blank_in_cycle} consecutive blank frames",
            attempts=len(strategies) * self._max_capture_attempts,
            blank_frames=blank_in_cycle,
        )

    @staticmethod
    def _is_blank_capture(rgb: np.ndarray) -> bool:
        # MEmu can intermittently return a valid all-black PNG from screencap.
        # Some faulty frames contain a handful of colored pixels at the top, so
        # checking only the maximum value is insufficient.
        if rgb.max() <= 8 and rgb.std() <= 0.25:
            return True
        visible_ratio = float(np.mean(np.max(rgb, axis=2) > 12))
        return bool(rgb.mean() <= 1.0 and visible_ratio < 0.002)

    def stop(self) -> None:
        self._started = False
