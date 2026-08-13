from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from inspect import Parameter, signature
from numbers import Real
from threading import Lock
from typing import Any, Protocol

from src.capture.base_capture import CaptureTemporarilyUnavailable
from src.capture.manager import CaptureManager
from src.capture.models import CaptureRequest, Frame
from src.core.cancellation import Cancelled, CancellationToken
from src.core.events import EventKind, EventSink, RuntimeEvent
from src.core.lifecycle import Lifecycle, RuntimeStatus


class Perception(Protocol):
    def analyze(self, image: Any, *, cancellation: CancellationToken | None = None) -> Mapping[str, Any]: ...


class FrameRecorder(Protocol):
    def record(self, frame: Frame, observation: Mapping[str, Any]) -> Any: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    poll_interval_seconds: float = 0.25
    capture_retry_seconds: float = 0.5

    def __post_init__(self) -> None:
        for name, value in (
            ("poll interval", self.poll_interval_seconds),
            ("capture retry", self.capture_retry_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number")
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


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
        recorder: FrameRecorder | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capture = capture
        self._perception = perception
        self._events = events
        self._lifecycle = lifecycle
        self._cancellation = cancellation
        self._settings = settings
        self._recorder = recorder
        self._recorder_failed = False
        self._clock = clock
        self._used = False
        self._used_lock = Lock()
        self._analyze_accepts_cancellation = self._detect_cancellation_support(perception.analyze)

    def _event(self, kind: EventKind, payload: dict[str, Any]) -> RuntimeEvent:
        return RuntimeEvent(kind=kind, emitted_at_monotonic=self._clock(), payload=payload)

    def _control_event(self, kind: EventKind, payload: dict[str, Any]) -> RuntimeEvent | None:
        """Lifecycle/error telemetry never controls cleanup; use a reliable clock fallback."""
        try:
            return self._event(kind, payload)
        except Exception:
            try:
                return RuntimeEvent(kind=kind, emitted_at_monotonic=time.monotonic(), payload=payload)
            except Exception:
                return None

    def _publish(self, event: RuntimeEvent, *, note_error: BaseException | None = None) -> None:
        """Event publication is best-effort; Lifecycle is the authoritative state."""
        try:
            self._events.publish(event)
        except Exception as publish_error:
            if note_error is not None:
                note_error.add_note(f"event publication also failed: {publish_error!r}")

    def _transition(self, target: RuntimeStatus) -> None:
        self._lifecycle.transition(target)
        event = self._control_event(EventKind.LIFECYCLE, {"status": target.value})
        if event is not None:
            self._publish(event)

    def _publish_error(self, exc: BaseException, *, phase: str) -> None:
        event = self._control_event(EventKind.ERROR, {"phase": phase, "error": repr(exc)})
        if event is not None:
            self._publish(event, note_error=exc)

    @staticmethod
    def _detect_cancellation_support(analyze: Callable[..., Any]) -> bool:
        try:
            parameters = signature(analyze).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(
            (parameter.name == "cancellation" and parameter.kind in {Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY})
            or parameter.kind is Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def _analyze(self, image: Any) -> Mapping[str, Any]:
        if self._analyze_accepts_cancellation:
            return self._perception.analyze(image, cancellation=self._cancellation)
        return self._perception.analyze(image)

    def _mark_failed(self, primary_error: BaseException) -> None:
        if self._lifecycle.status is RuntimeStatus.FAILED:
            return
        try:
            self._transition(RuntimeStatus.FAILED)
        except Exception as transition_error:
            primary_error.add_note(f"failed-state transition also failed: {transition_error!r}")

    def _capture_health_payload(self) -> dict[str, Any]:
        health = self._capture.health
        if health is None:
            return {}
        return {
            "capture_attempts": int(health.attempts),
            "valid_frames": int(health.valid_frames),
            "blank_frames": int(health.blank_frames),
            "capture_errors": int(health.operation_errors),
            "capture_failures": int(health.transient_failures),
            "capture_recoveries": int(health.recoveries),
            "capture_strategy": str(health.last_strategy),
        }

    def _record_frame(self, frame: Frame, observation: Mapping[str, Any]) -> None:
        if self._recorder is None or self._recorder_failed:
            return
        try:
            result = self._recorder.record(frame, observation)
            if not getattr(result, "saved", False):
                return
            self._publish(
                self._event(
                    EventKind.DATASET,
                    {
                        "status": "saved",
                        "saved_count": int(result.saved_count),
                        "reason": str(result.reason),
                        "path": result.relative_path,
                        "session_directory": str(result.session_directory),
                    },
                )
            )
        except Exception as exc:
            self._recorder_failed = True
            event = self._control_event(
                EventKind.DATASET,
                {"status": "disabled", "error": repr(exc)},
            )
            if event is not None:
                self._publish(event)

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
        with self._used_lock:
            if self._used:
                raise RuntimeError("BotRuntime is single-use")
            self._used = True
        if self._cancellation.cancelled:
            return 0

        processed = 0
        primary_error: BaseException | None = None
        cleanup_required = False
        capture_degraded = False

        try:
            cleanup_required = True
            self._transition(RuntimeStatus.STARTING)
            self._cancellation.raise_if_cancelled()
            self._capture.start()
            self._cancellation.raise_if_cancelled()
            self._transition(RuntimeStatus.RUNNING)

            while max_frames is None or processed < max_frames:
                self._cancellation.raise_if_cancelled()
                try:
                    frame = self._capture.next_frame(CaptureRequest.fresh_required())
                except CaptureTemporarilyUnavailable as exc:
                    capture_degraded = True
                    self._publish(
                        self._event(
                            EventKind.CAPTURE,
                            {
                                "status": "degraded",
                                "attempts": exc.attempts,
                                "blank_frames_in_cycle": exc.blank_frames,
                                **self._capture_health_payload(),
                            },
                        )
                    )
                    self._cancellation.wait(self._settings.capture_retry_seconds)
                    continue
                self._cancellation.raise_if_cancelled()
                health_payload = self._capture_health_payload()
                if capture_degraded:
                    capture_degraded = False
                    self._publish(
                        self._event(EventKind.CAPTURE, {"status": "recovered", **health_payload})
                    )
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
                            **health_payload,
                        },
                    )
                )
                self._cancellation.raise_if_cancelled()
                raw_observation = self._analyze(frame.image)
                self._cancellation.raise_if_cancelled()
                if not isinstance(raw_observation, Mapping):
                    raise TypeError("perception result must be a Mapping")
                if not all(isinstance(key, str) for key in raw_observation):
                    raise TypeError("perception result keys must be strings")
                observation = dict(raw_observation)
                observation["frame_id"] = frame.id
                self._cancellation.raise_if_cancelled()
                self._publish(self._event(EventKind.OBSERVATION, observation))
                self._record_frame(frame, observation)
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
                try:
                    if primary_error is None and self._lifecycle.status in {
                        RuntimeStatus.STARTING,
                        RuntimeStatus.RUNNING,
                        RuntimeStatus.PAUSED,
                    }:
                        self._transition(RuntimeStatus.STOPPING)
                except BaseException as cleanup_error:
                    if primary_error is None:
                        primary_error = cleanup_error
                    else:
                        primary_error.add_note(f"cleanup transition also failed: {cleanup_error!r}")
                finally:
                    try:
                        self._capture.stop()
                    except BaseException as stop_error:
                        if primary_error is not None:
                            primary_error.add_note(f"cleanup also failed: {stop_error!r}")
                        else:
                            primary_error = stop_error
                            try:
                                self._publish_error(primary_error, phase="cleanup")
                            except BaseException as telemetry_error:
                                primary_error.add_note(f"cleanup telemetry also failed: {telemetry_error!r}")

                if self._recorder is not None:
                    try:
                        self._recorder.close()
                    except BaseException as recorder_error:
                        event = self._control_event(
                            EventKind.DATASET,
                            {"status": "close-error", "error": repr(recorder_error)},
                        )
                        if event is not None:
                            self._publish(event)

                if primary_error is not None and self._lifecycle.status is not RuntimeStatus.FAILED:
                    try:
                        self._mark_failed(primary_error)
                    except BaseException as failed_transition_error:
                        primary_error.add_note(f"failed-state transition also failed: {failed_transition_error!r}")

                if primary_error is None and self._lifecycle.status is RuntimeStatus.STOPPING:
                    try:
                        self._transition(RuntimeStatus.STOPPED)
                    except BaseException as transition_error:
                        primary_error = transition_error

        if primary_error is not None:
            raise primary_error
        return processed
