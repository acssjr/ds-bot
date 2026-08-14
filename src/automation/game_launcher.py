from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from numbers import Real

from src.core.cancellation import CancellationToken
from src.core.events import EventKind, EventSink, RuntimeEvent
from src.device.session import DeviceSession
from src.recovery.app_supervisor import GAME_PACKAGE


@dataclass(frozen=True, slots=True)
class LaunchResult:
    started: bool
    package: str
    elapsed_seconds: float


class GameLaunchTimeout(TimeoutError):
    pass


class GameLauncher:
    """Bring the game to the foreground without issuing gameplay input."""

    def __init__(
        self,
        session: DeviceSession,
        *,
        events: EventSink | None = None,
        game_package: str = GAME_PACKAGE,
        timeout_seconds: float = 25.0,
        poll_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        for name, value in (("timeout", timeout_seconds), ("poll", poll_seconds)):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        self._session = session
        self._events = events
        self._game_package = game_package
        self._timeout = float(timeout_seconds)
        self._poll = float(poll_seconds)
        self._clock = clock

    def _publish(self, status: str, **payload: object) -> None:
        if self._events is None:
            return
        try:
            self._events.publish(
                RuntimeEvent(
                    EventKind.AUTOMATION,
                    self._clock(),
                    {"category": "app", "status": status, **payload},
                )
            )
        except Exception:
            pass

    def ensure_foreground(self, cancellation: CancellationToken) -> LaunchResult:
        started_at = self._clock()
        self._publish("connecting", device_serial=self._session.serial)
        if not self._session.connected:
            self._session.connect()
        cancellation.raise_if_cancelled()

        current = self._session.foreground_app()
        if current.package == self._game_package:
            elapsed = self._clock() - started_at
            self._publish("ready", package=current.package, started=False)
            return LaunchResult(False, current.package, elapsed)

        self._publish(
            "launching",
            package=self._game_package,
            previous_package=current.package,
        )
        self._session.start_app(self._game_package)
        while True:
            cancellation.raise_if_cancelled()
            current = self._session.foreground_app()
            if current.package == self._game_package:
                elapsed = self._clock() - started_at
                self._publish("ready", package=current.package, started=True)
                return LaunchResult(True, current.package, elapsed)
            if self._clock() - started_at >= self._timeout:
                self._publish(
                    "timeout",
                    package=self._game_package,
                    foreground_package=current.package,
                )
                raise GameLaunchTimeout(
                    f"{self._game_package} did not reach foreground within {self._timeout:.1f}s"
                )
            cancellation.wait(self._poll)
