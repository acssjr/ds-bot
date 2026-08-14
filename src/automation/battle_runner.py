from __future__ import annotations

import math
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Any, Protocol

import cv2
import numpy as np
from loguru import logger

from src.capture.base_capture import CaptureTemporarilyUnavailable
from src.capture.models import CaptureRequest, Frame
from src.core.cancellation import Cancelled, CancellationToken
from src.geometry.models import PixelPoint
from src.input.models import InputReceipt, TapCommand
from src.state.game_state import ScreenState


class BattlePhase(str, Enum):
    HOME = "HOME"
    WAIT_MATCHMAKING = "WAIT_MATCHMAKING"
    DRAFT_PICK = "DRAFT_PICK"
    RECOVERY_BONUS = "RECOVERY_BONUS"
    COMBAT = "COMBAT"
    ROUND_RESULT = "ROUND_RESULT"
    VICTORY_SPLASH = "VICTORY_SPLASH"
    MASTERY_DISTRIBUTION = "MASTERY_DISTRIBUTION"
    VICTORY_PACKAGE_READY = "VICTORY_PACKAGE_READY"
    VICTORY_PACKAGE_ANIMATING = "VICTORY_PACKAGE_ANIMATING"
    POST_BATTLE_OFFER = "POST_BATTLE_OFFER"
    LEAGUE_MENU = "LEAGUE_MENU"
    UNKNOWN = "UNKNOWN"


class ActionName(str, Enum):
    START_BATTLE = "start_battle"
    PICK_DRAFT = "pick_draft"
    SKIP_VICTORY = "skip_victory"
    SKIP_MASTERY = "skip_mastery"
    CONTINUE_VICTORY = "continue_victory"
    CLOSE_OFFER = "close_offer"
    RETURN_HOME = "return_home"


class Capture(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def next_frame(self, request: CaptureRequest) -> Frame: ...
    def invalidate_after_input(self) -> int: ...


class Perception(Protocol):
    def analyze(self, image: np.ndarray, *, cancellation: CancellationToken | None = None) -> Mapping[str, Any]: ...


class TapInput(Protocol):
    def execute(self, command: TapCommand) -> InputReceipt: ...


class ActionRecorder(Protocol):
    def record(self, frame: Frame, observation: Mapping[str, Any]) -> Any: ...
    def record_action(self, payload: Mapping[str, Any]) -> None: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class BattleSettings:
    poll_interval_seconds: float = 0.20
    capture_retry_seconds: float = 0.50
    stable_observations: int = 2
    postcondition_timeout_seconds: float = 12.0
    max_actions: int = 40
    max_runtime_seconds: float | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("poll interval", self.poll_interval_seconds),
            ("capture retry", self.capture_retry_seconds),
            ("postcondition timeout", self.postcondition_timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a real number")
            if not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name, value in (("stable observations", self.stable_observations), ("max actions", self.max_actions)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_runtime_seconds is not None:
            value = self.max_runtime_seconds
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError("max runtime must be a real number or None")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError("max runtime must be finite and positive")


@dataclass(frozen=True, slots=True)
class BattleResult:
    completed: bool
    frames: int
    actions: int
    final_phase: BattlePhase


@dataclass(frozen=True, slots=True)
class _Intent:
    name: ActionName
    point: tuple[float, float]
    success_phases: frozenset[BattlePhase]
    metadata: Mapping[str, Any]


@dataclass(slots=True)
class _Pending:
    intent: _Intent
    command: TapCommand
    receipt: InputReceipt
    issued_at: float
    before_phase: BattlePhase
    before_signature: np.ndarray


class ActionPostconditionTimeout(RuntimeError):
    pass


class BattleRunner:
    _DRAFT_X = (0.167, 0.500, 0.833)

    def __init__(
        self,
        *,
        capture: Capture,
        perception: Perception,
        input_backend: TapInput,
        cancellation: CancellationToken,
        settings: BattleSettings = BattleSettings(),
        recorder: ActionRecorder | None = None,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capture = capture
        self._perception = perception
        self._input = input_backend
        self._cancellation = cancellation
        self._settings = settings
        self._recorder = recorder
        self._rng = rng or random.Random()
        self._clock = clock
        self._command_sequence = 0

    @staticmethod
    def _screen(observation: Mapping[str, Any]) -> ScreenState:
        raw = observation.get("screen", ScreenState.UNKNOWN)
        try:
            return raw if isinstance(raw, ScreenState) else ScreenState(raw)
        except (TypeError, ValueError):
            return ScreenState.UNKNOWN

    @classmethod
    def phase_for(cls, observation: Mapping[str, Any]) -> BattlePhase:
        screen = cls._screen(observation)
        if screen is ScreenState.HOME:
            return BattlePhase.HOME
        if screen is ScreenState.WAIT_MATCHMAKING:
            return BattlePhase.WAIT_MATCHMAKING
        if screen is ScreenState.DRAFT_SCREEN:
            return (
                BattlePhase.RECOVERY_BONUS
                if observation.get("draft_variant") == "recovery_bonus"
                else BattlePhase.DRAFT_PICK
            )
        if screen is ScreenState.COMBAT:
            return BattlePhase.COMBAT
        if screen is ScreenState.ROUND_RESULT:
            return BattlePhase.ROUND_RESULT
        if screen is ScreenState.POST_BATTLE_OFFER:
            return BattlePhase.POST_BATTLE_OFFER
        if screen is ScreenState.LEAGUE_MENU:
            return BattlePhase.LEAGUE_MENU
        if screen is ScreenState.VICTORY_SUMMARY:
            phase = observation.get("victory_phase")
            return {
                "splash": BattlePhase.VICTORY_SPLASH,
                "mastery_distribution": BattlePhase.MASTERY_DISTRIBUTION,
                "package_ready": BattlePhase.VICTORY_PACKAGE_READY,
                "package_animating": BattlePhase.VICTORY_PACKAGE_ANIMATING,
            }.get(str(phase), BattlePhase.UNKNOWN)
        return BattlePhase.UNKNOWN

    @staticmethod
    def _signature(image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (32, 48), interpolation=cv2.INTER_AREA)

    @staticmethod
    def _visual_difference(before: np.ndarray, after: np.ndarray) -> float:
        return float(np.mean(cv2.absdiff(before, after))) / 255.0

    @staticmethod
    def _pixel(point: tuple[float, float], frame: Frame) -> PixelPoint:
        x = min(frame.size.width - 1, max(0, round(point[0] * (frame.size.width - 1))))
        y = min(frame.size.height - 1, max(0, round(point[1] * (frame.size.height - 1))))
        return PixelPoint(x, y)

    def _intent(self, phase: BattlePhase, observation: Mapping[str, Any]) -> _Intent | None:
        if phase is BattlePhase.HOME:
            return _Intent(
                ActionName.START_BATTLE,
                (0.50, 0.75),
                frozenset({BattlePhase.WAIT_MATCHMAKING, BattlePhase.DRAFT_PICK, BattlePhase.COMBAT}),
                {},
            )
        if phase in {BattlePhase.DRAFT_PICK, BattlePhase.RECOVERY_BONUS}:
            raw_slots = observation.get("draft_available_slots", ())
            slots = tuple(slot for slot in raw_slots if type(slot) is int and 0 <= slot <= 2)
            if not slots:
                return None
            slot = self._rng.choice(slots)
            return _Intent(
                ActionName.PICK_DRAFT,
                (self._DRAFT_X[slot], 0.54),
                frozenset({BattlePhase.COMBAT}),
                {"slot": slot, "variant": phase.value},
            )
        if phase is BattlePhase.VICTORY_SPLASH:
            return _Intent(
                ActionName.SKIP_VICTORY,
                (0.50, 0.82),
                frozenset({BattlePhase.MASTERY_DISTRIBUTION, BattlePhase.VICTORY_PACKAGE_READY, BattlePhase.VICTORY_PACKAGE_ANIMATING}),
                {},
            )
        if phase is BattlePhase.MASTERY_DISTRIBUTION:
            return _Intent(
                ActionName.SKIP_MASTERY,
                (0.50, 0.82),
                frozenset({BattlePhase.VICTORY_PACKAGE_READY, BattlePhase.VICTORY_PACKAGE_ANIMATING}),
                {},
            )
        if phase is BattlePhase.VICTORY_PACKAGE_READY and observation.get("continue_visible") is True:
            return _Intent(
                ActionName.CONTINUE_VICTORY,
                (0.71, 0.91),
                frozenset({BattlePhase.VICTORY_PACKAGE_ANIMATING, BattlePhase.LEAGUE_MENU, BattlePhase.POST_BATTLE_OFFER, BattlePhase.HOME}),
                {},
            )
        if phase is BattlePhase.POST_BATTLE_OFFER and observation.get("offer_close_visible") is True:
            raw = observation.get("offer_close_point")
            if not isinstance(raw, (tuple, list)) or len(raw) != 2:
                return None
            point = (float(raw[0]), float(raw[1]))
            if not (0.75 <= point[0] <= 0.95 and 0.20 <= point[1] <= 0.45):
                return None
            return _Intent(
                ActionName.CLOSE_OFFER,
                point,
                frozenset({BattlePhase.HOME}),
                {},
            )
        if phase is BattlePhase.LEAGUE_MENU:
            return _Intent(
                ActionName.RETURN_HOME,
                (0.50, 0.92),
                frozenset({BattlePhase.HOME, BattlePhase.POST_BATTLE_OFFER}),
                {},
            )
        return None

    def _audit(self, payload: Mapping[str, Any]) -> None:
        if self._recorder is None:
            return
        try:
            self._recorder.record_action(payload)
        except Exception as exc:
            logger.warning("Action audit failed without retrying input: {!r}", exc)

    def _issue(self, intent: _Intent, frame: Frame, phase: BattlePhase) -> _Pending:
        self._command_sequence += 1
        command = TapCommand(
            command_id=f"battle-{self._command_sequence:03d}-{intent.name.value}",
            point=self._pixel(intent.point, frame),
        )
        receipt = self._input.execute(command)
        generation = self._capture.invalidate_after_input()
        pending = _Pending(
            intent=intent,
            command=command,
            receipt=receipt,
            issued_at=self._clock(),
            before_phase=phase,
            before_signature=self._signature(frame.image),
        )
        self._audit(
            {
                "event": "issued",
                "command_id": command.command_id,
                "action": intent.name.value,
                "point": command.point.as_tuple(),
                "frame_id": frame.id,
                "phase": phase.value,
                "capture_generation": generation,
                "metadata": dict(intent.metadata),
            }
        )
        logger.info("ACTION {} at {} from {}", intent.name.value, command.point.as_tuple(), phase.value)
        return pending

    def _resolved(self, pending: _Pending, phase: BattlePhase, frame: Frame) -> bool:
        if phase not in pending.intent.success_phases:
            return False
        if phase is pending.before_phase:
            difference = self._visual_difference(pending.before_signature, self._signature(frame.image))
            return difference >= 0.035
        return True

    def run(self) -> BattleResult:
        started_at = self._clock()
        frames = 0
        actions = 0
        last_phase = BattlePhase.UNKNOWN
        stable_count = 0
        pending: _Pending | None = None
        battle_seen = False
        battle_finished = False
        self._capture.start()
        try:
            while True:
                self._cancellation.raise_if_cancelled()
                if (
                    self._settings.max_runtime_seconds is not None
                    and self._clock() - started_at > self._settings.max_runtime_seconds
                ):
                    raise TimeoutError("battle runtime exceeded configured maximum")
                try:
                    frame = self._capture.next_frame(CaptureRequest.fresh_required())
                except CaptureTemporarilyUnavailable:
                    self._cancellation.wait(self._settings.capture_retry_seconds)
                    continue

                raw = self._perception.analyze(frame.image, cancellation=self._cancellation)
                observation = dict(raw)
                observation["frame_id"] = frame.id
                phase = self.phase_for(observation)
                frames += 1
                if self._recorder is not None:
                    self._recorder.record(frame, observation)

                if phase is last_phase:
                    stable_count += 1
                else:
                    last_phase = phase
                    stable_count = 1
                logger.info("STATE frame={} phase={} confidence={:.1%}", frame.id, phase.value, float(observation.get("confidence", 0.0)))

                if phase in {
                    BattlePhase.WAIT_MATCHMAKING,
                    BattlePhase.DRAFT_PICK,
                    BattlePhase.RECOVERY_BONUS,
                    BattlePhase.COMBAT,
                    BattlePhase.ROUND_RESULT,
                }:
                    battle_seen = True
                if phase in {
                    BattlePhase.VICTORY_SPLASH,
                    BattlePhase.MASTERY_DISTRIBUTION,
                    BattlePhase.VICTORY_PACKAGE_READY,
                    BattlePhase.VICTORY_PACKAGE_ANIMATING,
                    BattlePhase.LEAGUE_MENU,
                }:
                    battle_finished = battle_seen or battle_finished

                if pending is not None:
                    if self._resolved(pending, phase, frame):
                        self._audit(
                            {
                                "event": "resolved",
                                "command_id": pending.command.command_id,
                                "action": pending.intent.name.value,
                                "frame_id": frame.id,
                                "phase": phase.value,
                            }
                        )
                        pending = None
                    elif self._clock() - pending.issued_at > self._settings.postcondition_timeout_seconds:
                        self._audit(
                            {
                                "event": "timeout",
                                "command_id": pending.command.command_id,
                                "action": pending.intent.name.value,
                                "frame_id": frame.id,
                                "phase": phase.value,
                            }
                        )
                        raise ActionPostconditionTimeout(
                            f"{pending.intent.name.value} did not reach a visual postcondition"
                        )
                    self._cancellation.wait(self._settings.poll_interval_seconds)
                    continue

                if phase is BattlePhase.HOME and battle_finished:
                    return BattleResult(True, frames, actions, phase)

                if stable_count >= self._settings.stable_observations:
                    intent = self._intent(phase, observation)
                    if intent is not None:
                        if actions >= self._settings.max_actions:
                            raise RuntimeError("battle action budget exhausted")
                        pending = self._issue(intent, frame, phase)
                        actions += 1

                self._cancellation.wait(self._settings.poll_interval_seconds)
        except Cancelled:
            return BattleResult(False, frames, actions, last_phase)
        finally:
            try:
                self._capture.stop()
            finally:
                if self._recorder is not None:
                    self._recorder.close()
