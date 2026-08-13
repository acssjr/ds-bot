from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from loguru import logger

from src.device.session import DeviceSession


GAME_PACKAGE = "com.QuestLab.DraftWar"
AD_SCREENS = {"WATCHING_AD", "AD_REWARD_GRANTED"}


class RewardedAdAppSupervisor:
    """Return to the game if a rewarded ad opens an external application."""

    def __init__(
        self,
        session: DeviceSession,
        *,
        game_package: str = GAME_PACKAGE,
        armed_seconds: float = 240.0,
        check_interval_seconds: float = 1.0,
        recovery_delay_seconds: float = 0.4,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._game_package = game_package
        self._armed_seconds = armed_seconds
        self._check_interval_seconds = check_interval_seconds
        self._recovery_delay_seconds = recovery_delay_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._armed_until: float | None = None
        self._next_check_at = 0.0

    def after_observation(self, observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
        now = self._clock()
        observed_screen = observation.get("screen", "")
        screen = str(getattr(observed_screen, "value", observed_screen))
        if screen in AD_SCREENS:
            self._armed_until = now + self._armed_seconds
        if self._armed_until is None or now > self._armed_until:
            return None
        if now < self._next_check_at:
            return None
        self._next_check_at = now + self._check_interval_seconds

        foreground = self._session.foreground_app()
        if foreground.package == self._game_package:
            return None

        external_package = foreground.package
        # One observed excursion authorizes one bounded recovery sequence. A
        # later ad screen can arm the supervisor again, including ad 2 of 2.
        self._armed_until = None
        logger.warning(
            "Rewarded ad opened external app {}; returning to Draft Showdown",
            external_package,
        )
        for attempt in (1, 2):
            self._session.press_back()
            self._sleeper(self._recovery_delay_seconds)
            returned = self._session.foreground_app()
            if returned.package == self._game_package:
                return {
                    "status": "recovered",
                    "method": "android_back",
                    "attempts": attempt,
                    "external_package": external_package,
                    "foreground_package": returned.package,
                }

        self._session.start_app(self._game_package)
        self._sleeper(self._recovery_delay_seconds)
        returned = self._session.foreground_app()
        if returned.package == self._game_package:
            return {
                "status": "recovered",
                "method": "relaunch_game",
                "attempts": 1,
                "external_package": external_package,
                "foreground_package": returned.package,
            }

        self._session.stop_app(self._game_package)
        self._session.start_app(self._game_package)
        self._sleeper(self._recovery_delay_seconds)
        returned = self._session.foreground_app()
        return {
            "status": "recovered" if returned.package == self._game_package else "failed",
            "method": "restart_game",
            "attempts": 1,
            "external_package": external_package,
            "foreground_package": returned.package,
        }
