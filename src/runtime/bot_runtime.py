from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from numbers import Real
from typing import Any, Protocol

from src.capture.manager import CaptureManager
from src.capture.models import CaptureRequest
from src.core.cancellation import Cancelled, CancellationToken
from src.core.events import EventKind, EventSink, RuntimeEvent
from src.core.lifecycle import Lifecycle, RuntimeStatus


class Perception(Protocol):
    def analyze(self, image: Any) -> Mapping[str, Any]: ...


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
        events: EventSink,
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
        self._used = False

    def _event(self, kind: EventKind, payload: dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(kind=kind, emitted_at_monotonic=self._clock(), payload=payload)

    def _publish(self, event: RuntimeEvent, *, note_error: BaseException | None = None) -> None:
        """Event publication is best-effort; Lifecycle is the authoritative state."""
        try:
            self._events.publish(event)
        except Exception as publish_error:
            if note_error is not None:
                note_error.add_note(f"event publication also failed: {publish_error!r}")

    def _transition(self, target: RuntimeStatus) -> None:
        self._lifecycle.transition(target)
        self._publish(self._event(EventKind.LIFECYCLE, {"status": target.value}))

    def _publish_error(self, exc: BaseException, *, phase: str) -> None:
        self._publish(self._event(EventKind.ERROR, {"phase": phase, "error": repr(exc)}), note_error=exc)

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
        if self._used:
            raise RuntimeError("BotRuntime is single-use")
        self._used = True
        if self._cancellation.cancelled:
            return 0

        processed = 0
        primary_error: BaseException | None = None
        cleanup_required = False

        try:
            cleanup_required = True
            self._transition(RuntimeStatus.STARTING)
            self._cancellation.raise_if_cancelled()
            self._capture.start()
            self._cancellation.raise_if_cancelled()
            self._transition(RuntimeStatus.RUNNING)

            while max_frames is None or processed < max_frames:
                self._cancellation.raise_if_cancelled()
                frame = self._capture.next_frame(CaptureRequest.fresh_required())
                self._cancellation.raise_if_cancelled()
                self._publish(
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
                self._cancellation.raise_if_cancelled()
                raw_observation = self._perception.analyze(frame.image)
                self._cancellation.raise_if_cancelled()
                if not isinstance(raw_observation, Mapping):
                    raise TypeError("perception result must be a Mapping")
                if not all(isinstance(key, str) for key in raw_observation):
                    raise TypeError("perception result keys must be strings")
                observation = dict(raw_observation)
                observation["frame_id"] = frame.id
                self._cancellation.raise_if_cancelled()
                self._publish(self._event(EventKind.OBSERVATION, observation))
                processed += 1
                if max_frames is None or processed < max_frames:
                    self._cancellation.raise_if_cancelled()
                    self._cancellation.wait(self._settings.poll_interval_seconds)
        except Cancelled:
            pass
        except Exception as exc:
            primary_error = exc
            self._publish_error(primary_error, phase="run")
            self._mark_failed(primary_error)
        finally:
            if cleanup_required:
                if primary_error is None and self._lifecycle.status in {
                    RuntimeStatus.STARTING,
                    RuntimeStatus.RUNNING,
                    RuntimeStatus.PAUSED,
                }:
                    try:
                        self._transition(RuntimeStatus.STOPPING)
                    except Exception as transition_error:
                        primary_error = transition_error
                        self._publish_error(primary_error, phase="cleanup")
                        self._mark_failed(primary_error)
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

                if primary_error is None and self._lifecycle.status is RuntimeStatus.STOPPING:
                    try:
                        self._transition(RuntimeStatus.STOPPED)
                    except Exception as transition_error:
                        primary_error = transition_error
                        self._publish_error(primary_error, phase="cleanup")
                        self._mark_failed(primary_error)

        if primary_error is not None:
            raise primary_error
        return processed
