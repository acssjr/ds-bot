from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real
from typing import Any, Protocol

from src.capture.manager import CaptureManager
from src.capture.models import CaptureRequest
from src.core.cancellation import Cancelled, CancellationToken
from src.core.events import EventBus, EventKind, RuntimeEvent
from src.core.lifecycle import Lifecycle, RuntimeStatus


class Perception(Protocol):
    def analyze(self, image: Any) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    poll_interval_seconds: float = 0.25

    def __post_init__(self) -> None:
        value = self.poll_interval_seconds
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError("poll interval must be a real number")
        if not math.isfinite(value):
            raise ValueError("poll interval must be finite")
        if value < 0:
            raise ValueError("poll interval must be non-negative")


class BotRuntime:
    def __init__(
        self,
        *,
        capture: CaptureManager,
        perception: Perception,
        events: EventBus,
        lifecycle: Lifecycle,
        cancellation: CancellationToken,
        settings: RuntimeSettings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capture = capture
        self._perception = perception
        self._events = events
        self._lifecycle = lifecycle
        self._cancellation = cancellation
        self._settings = settings
        self._clock = clock

    def _event(self, kind: EventKind, payload: dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(kind=kind, emitted_at_monotonic=self._clock(), payload=payload)

    def _transition(self, target: RuntimeStatus) -> None:
        self._lifecycle.transition(target)
        self._events.publish(self._event(EventKind.LIFECYCLE, {"status": target.value}))

    def _publish_error(self, exc: BaseException, *, phase: str) -> None:
        try:
            self._events.publish(self._event(EventKind.ERROR, {"phase": phase, "error": repr(exc)}))
        except Exception as publish_error:
            exc.add_note(f"error publication also failed: {publish_error!r}")

    def _mark_failed(self, primary_error: BaseException) -> None:
        if self._lifecycle.status is RuntimeStatus.FAILED:
            return
        try:
            self._transition(RuntimeStatus.FAILED)
        except Exception as transition_error:
            primary_error.add_note(f"failed-state transition also failed: {transition_error!r}")

    @staticmethod
    def _validate_max_frames(max_frames: int | None) -> None:
        if max_frames is None:
            return
        if isinstance(max_frames, bool) or not isinstance(max_frames, int):
            raise TypeError("max_frames must be a positive integer or None")
        if max_frames <= 0:
            raise ValueError("max_frames must be a positive integer or None")

    def run(self, max_frames: int | None = None) -> int:
        self._validate_max_frames(max_frames)
        processed = 0
        primary_error: BaseException | None = None

        try:
            self._transition(RuntimeStatus.STARTING)
            self._capture.start()
            self._transition(RuntimeStatus.RUNNING)

            while max_frames is None or processed < max_frames:
                self._cancellation.raise_if_cancelled()
                frame = self._capture.next_frame(CaptureRequest.fresh_required())
                self._events.publish(
                    self._event(
                        EventKind.FRAME,
                        {
                            "frame_id": frame.id,
                            "backend": frame.backend.value,
                            "width": frame.size.width,
                            "height": frame.size.height,
                            "device_serial": frame.device_serial,
                            "connection_generation": frame.connection_generation,
                            "capture_generation": frame.capture_generation,
                        },
                    )
                )
                observation = dict(self._perception.analyze(frame.image))
                observation["frame_id"] = frame.id
                self._events.publish(self._event(EventKind.OBSERVATION, observation))
                processed += 1
                if max_frames is None or processed < max_frames:
                    self._cancellation.wait(self._settings.poll_interval_seconds)
        except Cancelled:
            pass
        except Exception as exc:
            primary_error = exc
            self._publish_error(primary_error, phase="run")
            self._mark_failed(primary_error)
        finally:
            try:
                self._capture.stop()
            except Exception as stop_error:
                if primary_error is not None:
                    primary_error.add_note(f"cleanup also failed: {stop_error!r}")
                    self._publish_error(stop_error, phase="cleanup")
                else:
                    primary_error = stop_error
                    self._publish_error(primary_error, phase="cleanup")
                    self._mark_failed(primary_error)

            if primary_error is None and self._lifecycle.status in {
                RuntimeStatus.STARTING,
                RuntimeStatus.RUNNING,
                RuntimeStatus.PAUSED,
            }:
                try:
                    self._transition(RuntimeStatus.STOPPING)
                    self._transition(RuntimeStatus.STOPPED)
                except Exception as transition_error:
                    primary_error = transition_error
                    self._publish_error(primary_error, phase="cleanup")
                    self._mark_failed(primary_error)

        if primary_error is not None:
            raise primary_error
        return processed
