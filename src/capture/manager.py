from __future__ import annotations

import time
from collections.abc import Callable

from src.capture.base_capture import CaptureSource
from src.capture.models import CaptureRequest, Frame, Freshness


class CaptureManager:
    def __init__(
        self,
        source: CaptureSource,
        *,
        device_serial: str,
        connection_generation: Callable[[], int],
        clock: Callable[[], float] = time.monotonic,
    ):
        self._source = source
        self._device_serial = device_serial
        self._connection_generation = connection_generation
        self._clock = clock
        self._last_frame: Frame | None = None
        self._next_frame_id = 1
        self._capture_generation = 0
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        try:
            self._source.start()
        except BaseException as primary_error:
            try:
                self._source.stop()
            except BaseException as rollback_error:
                primary_error.add_note(f"rollback also failed: {rollback_error!r}")
            raise
        self._last_frame = None
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        try:
            self._source.stop()
        finally:
            self._started = False
            self._last_frame = None

    def invalidate_after_input(self) -> int:
        self._capture_generation += 1
        self._last_frame = None
        return self._capture_generation

    def next_frame(self, request: CaptureRequest) -> Frame:
        if not self._started:
            raise RuntimeError("capture manager is not started")
        if self._capture_generation < request.minimum_generation:
            raise ValueError("capture generation was not invalidated for requested action")

        connection_generation = self._connection_generation()
        cached = self._last_frame
        if (
            request.freshness is Freshness.REUSE_OK
            and cached is not None
            and cached.capture_generation == self._capture_generation
            and cached.connection_generation == connection_generation
            and cached.age_seconds(self._clock()) <= request.max_age_seconds
        ):
            return cached

        captured = self._source.capture()
        frame = Frame.from_capture(
            captured,
            frame_id=self._next_frame_id,
            device_serial=self._device_serial,
            connection_generation=connection_generation,
            capture_generation=self._capture_generation,
        )
        self._next_frame_id += 1
        self._last_frame = frame
        return frame
