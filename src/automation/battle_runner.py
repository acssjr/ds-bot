from __future__ import annotations

import math
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
from src.core.events import EventKind, EventSink, RuntimeEvent
from src.geometry.models import PixelPoint
from src.input.models import InputReceipt, TapCommand
from src.state.game_state import ScreenState
from src.strategy.draft_policy import DraftPolicy
from src.strategy.unit_knowledge import unit_for
from src.vision.draft_reader import DraftCard


class BattlePhase(str, Enum):
    HOME = "HOME"
    WAIT_MATCHMAKING = "WAIT_MATCHMAKING"
    DRAFT_PICK = "DRAFT_PICK"
    RECOVERY_BONUS = "RECOVERY_BONUS"
    COMBAT = "COMBAT"
    ROUND_RESULT = "ROUND_RESULT"
    VICTORY_SPLASH = "VICTORY_SPLASH"
    MASTERY_DISTRIBUTION = "MASTERY_DISTRIBUTION"
    DEFEAT_DISTRIBUTION = "DEFEAT_DISTRIBUTION"
    VICTORY_PACKAGE_READY = "VICTORY_PACKAGE_READY"
    VICTORY_PACKAGE_ANIMATING = "VICTORY_PACKAGE_ANIMATING"
    DOUBLE_BITS = "DOUBLE_BITS"
    MASTERY_BOOST = "MASTERY_BOOST"
    BIT_PACK_OPENING = "BIT_PACK_OPENING"
    NEW_UNIT_UNLOCKED = "NEW_UNIT_UNLOCKED"
    WATCHING_AD = "WATCHING_AD"
    AD_REWARD_GRANTED = "AD_REWARD_GRANTED"
    POST_BATTLE_OFFER = "POST_BATTLE_OFFER"
    LEAGUE_MENU = "LEAGUE_MENU"
    UNKNOWN = "UNKNOWN"


class ActionName(str, Enum):
    START_BATTLE = "start_battle"
    PICK_DRAFT = "pick_draft"
    SKIP_VICTORY = "skip_victory"
    SKIP_MASTERY = "skip_mastery"
    SKIP_DEFEAT_DISTRIBUTION = "skip_defeat_distribution"
    CONTINUE_VICTORY = "continue_victory"
    CLAIM_VICTORY_AD = "claim_victory_ad"
    CLAIM_DOUBLE_BITS_AD = "claim_double_bits_ad"
    CONTINUE_DOUBLE_BITS = "continue_double_bits"
    APPLY_MASTERY_BOOST = "apply_mastery_boost"
    CONTINUE_MASTERY = "continue_mastery"
    SKIP_BIT_PACK = "skip_bit_pack"
    CONTINUE_NEW_UNIT = "continue_new_unit"
    CLOSE_REWARDED_AD = "close_rewarded_ad"
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


class RecoverySupervisor(Protocol):
    def after_observation(self, observation: Mapping[str, Any]) -> Mapping[str, Any] | None: ...


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
        events: EventSink | None = None,
        draft_policy: DraftPolicy | None = None,
        recovery: RecoverySupervisor | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._capture = capture
        self._perception = perception
        self._input = input_backend
        self._cancellation = cancellation
        self._settings = settings
        self._recorder = recorder
        self._events = events
        self._draft_policy = draft_policy or DraftPolicy()
        self._recovery = recovery
        self._draft_history: dict[str, int] = {}
        self._draft_tiers: dict[str, int] = {}
        self._victory_reward_claimed = False
        self._double_bits_claimed = False
        self._boost_attempted_slots: set[int] = set()
        self._bit_pack_tapped = False
        self._clock = clock
        self._command_sequence = 0

    def _publish_automation(self, status: str, **payload: object) -> None:
        if self._events is None:
            return
        try:
            self._events.publish(
                RuntimeEvent(
                    EventKind.AUTOMATION,
                    self._clock(),
                    {"category": "battle", "status": status, **payload},
                )
            )
        except Exception:
            pass

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
        if screen is ScreenState.DEFEAT_SUMMARY:
            return BattlePhase.DEFEAT_DISTRIBUTION
        if screen is ScreenState.POST_BATTLE_OFFER:
            return BattlePhase.POST_BATTLE_OFFER
        if screen is ScreenState.LEAGUE_MENU:
            return BattlePhase.LEAGUE_MENU
        if screen is ScreenState.DOUBLE_BITS:
            return BattlePhase.DOUBLE_BITS
        if screen is ScreenState.MASTERY_BOOST:
            return BattlePhase.MASTERY_BOOST
        if screen is ScreenState.BIT_PACK_OPENING:
            return BattlePhase.BIT_PACK_OPENING
        if screen is ScreenState.NEW_UNIT_UNLOCKED:
            return BattlePhase.NEW_UNIT_UNLOCKED
        if screen is ScreenState.WATCHING_AD:
            return BattlePhase.WATCHING_AD
        if screen is ScreenState.AD_REWARD_GRANTED:
            return BattlePhase.AD_REWARD_GRANTED
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
    def _draft_fingerprint(raw_choices: object) -> tuple[tuple[object, ...], ...]:
        if not isinstance(raw_choices, (tuple, list)):
            return ()
        result: list[tuple[object, ...]] = []
        for raw in raw_choices:
            if not isinstance(raw, Mapping):
                continue
            result.append(
                (
                    raw.get("slot"),
                    str(raw.get("unit") or ""),
                    str(raw.get("effect") or "unknown"),
                    raw.get("magnitude", 1),
                    str(raw.get("text") or ""),
                )
            )
        return tuple(result)

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
            raw_choices = observation.get("draft_choices", ())
            cards: list[DraftCard] = []
            if isinstance(raw_choices, (tuple, list)):
                for raw in raw_choices:
                    if not isinstance(raw, Mapping):
                        continue
                    try:
                        slot = int(raw.get("slot", -1))
                        if slot not in slots:
                            continue
                        effect = str(raw.get("effect") or "unknown")
                        if effect not in {"add", "multiply", "upgrade", "transform", "unknown"}:
                            effect = "unknown"
                        cards.append(
                            DraftCard(
                                slot=slot,
                                text=str(raw.get("text") or "OCR_UNREADABLE"),
                                unit=str(raw["unit"]) if raw.get("unit") else None,
                                effect=effect,
                                magnitude=max(1, int(raw.get("magnitude", 1))),
                                confidence=min(
                                    1.0,
                                    max(0.0, float(raw.get("confidence", 0.0))),
                                ),
                            )
                        )
                    except (TypeError, ValueError):
                        continue
            known_slots = {card.slot for card in cards}
            cards.extend(
                DraftCard(slot, "OCR_UNREADABLE", None, "unknown", 1, 0.0)
                for slot in slots
                if slot not in known_slots
            )
            decision = self._draft_policy.choose(
                cards,
                history=self._draft_history,
                tiers=self._draft_tiers,
                variant=str(observation.get("draft_variant") or "normal_pick"),
                enemy_units=(
                    tuple(observation.get("enemy_units", ()))
                    if isinstance(observation.get("enemy_units", ()), (tuple, list))
                    else ()
                ),
                enemy_pressure=str(
                    observation.get("enemy_board_pressure") or "unknown"
                ),
            )
            slot = decision.selected_slot
            selected = next(card for card in cards if card.slot == slot)
            return _Intent(
                ActionName.PICK_DRAFT,
                (self._DRAFT_X[slot], 0.54),
                frozenset(
                    {
                        BattlePhase.DRAFT_PICK,
                        BattlePhase.RECOVERY_BONUS,
                        BattlePhase.COMBAT,
                    }
                ),
                {
                    "slot": slot,
                    "variant": phase.value,
                    "selected_unit": selected.unit,
                    "selected_effect": selected.effect,
                    "selected_magnitude": selected.magnitude,
                    "selected_initial_spawn": (
                        knowledge.early_spawn
                        if selected.unit is not None
                        and (knowledge := unit_for(selected.unit)) is not None
                        else 1
                    ),
                    "decision": decision.payload(),
                    "draft_fingerprint": self._draft_fingerprint(raw_choices),
                },
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
        if phase is BattlePhase.DEFEAT_DISTRIBUTION:
            return _Intent(
                ActionName.SKIP_DEFEAT_DISTRIBUTION,
                (0.50, 0.82),
                frozenset({BattlePhase.MASTERY_BOOST}),
                {"match_outcome": "defeat"},
            )
        if (
            phase is BattlePhase.VICTORY_PACKAGE_READY
            and observation.get("reward_ad_available") is True
            and not self._victory_reward_claimed
        ):
            return _Intent(
                ActionName.CLAIM_VICTORY_AD,
                (0.50, 0.75),
                frozenset(
                    {
                        BattlePhase.WATCHING_AD,
                        BattlePhase.AD_REWARD_GRANTED,
                        BattlePhase.DOUBLE_BITS,
                    }
                ),
                {"set_flag": "victory_reward_claimed", "reward": "victory_package"},
            )
        if phase is BattlePhase.VICTORY_PACKAGE_READY and observation.get("continue_visible") is True:
            return _Intent(
                ActionName.CONTINUE_VICTORY,
                (0.71, 0.91),
                frozenset(
                    {
                        BattlePhase.VICTORY_PACKAGE_ANIMATING,
                        BattlePhase.DOUBLE_BITS,
                        BattlePhase.MASTERY_BOOST,
                        BattlePhase.BIT_PACK_OPENING,
                        BattlePhase.NEW_UNIT_UNLOCKED,
                        BattlePhase.LEAGUE_MENU,
                        BattlePhase.POST_BATTLE_OFFER,
                        BattlePhase.HOME,
                    }
                ),
                {},
            )
        if phase is BattlePhase.AD_REWARD_GRANTED and observation.get("safe_to_close") is True:
            raw = observation.get("ad_close_point")
            if not isinstance(raw, (tuple, list)) or len(raw) != 2:
                return None
            point = (float(raw[0]), float(raw[1]))
            safe_corner = 0.0 <= point[1] <= 0.18 and (
                0.0 <= point[0] <= 0.35 or 0.70 <= point[0] <= 1.0
            )
            if not safe_corner:
                return None
            return _Intent(
                ActionName.CLOSE_REWARDED_AD,
                point,
                frozenset(
                    {
                        BattlePhase.WATCHING_AD,
                        BattlePhase.DOUBLE_BITS,
                        BattlePhase.MASTERY_BOOST,
                        BattlePhase.BIT_PACK_OPENING,
                        BattlePhase.NEW_UNIT_UNLOCKED,
                        BattlePhase.VICTORY_PACKAGE_READY,
                        BattlePhase.LEAGUE_MENU,
                        BattlePhase.HOME,
                    }
                ),
                {"reward_confirmed": True},
            )
        if phase is BattlePhase.DOUBLE_BITS:
            if observation.get("double_bits_ad_available") is True and not self._double_bits_claimed:
                return _Intent(
                    ActionName.CLAIM_DOUBLE_BITS_AD,
                    (0.50, 0.72),
                    frozenset(
                        {
                            BattlePhase.WATCHING_AD,
                            BattlePhase.AD_REWARD_GRANTED,
                            BattlePhase.MASTERY_BOOST,
                            BattlePhase.BIT_PACK_OPENING,
                            BattlePhase.NEW_UNIT_UNLOCKED,
                        }
                    ),
                    {"set_flag": "double_bits_claimed", "reward": "double_bits"},
                )
            return _Intent(
                ActionName.CONTINUE_DOUBLE_BITS,
                (0.50, 0.84),
                frozenset(
                    {
                        BattlePhase.MASTERY_BOOST,
                        BattlePhase.BIT_PACK_OPENING,
                        BattlePhase.NEW_UNIT_UNLOCKED,
                        BattlePhase.LEAGUE_MENU,
                        BattlePhase.HOME,
                    }
                ),
                {},
            )
        if phase is BattlePhase.MASTERY_BOOST:
            raw_slots = observation.get("boost_available_slots", ())
            slots = tuple(slot for slot in raw_slots if type(slot) is int and 0 <= slot <= 3)
            resources = observation.get("resources")
            raw_currency = resources.get("mastery_currency") if isinstance(resources, Mapping) else None
            currency_available = not isinstance(raw_currency, int) or raw_currency > 0
            remaining = tuple(
                slot for slot in slots if slot not in self._boost_attempted_slots
            )
            if remaining and currency_available:
                slot = remaining[0]
                return _Intent(
                    ActionName.APPLY_MASTERY_BOOST,
                    (0.125 + slot * 0.25, 0.615),
                    frozenset(
                        {
                            BattlePhase.MASTERY_BOOST,
                            BattlePhase.BIT_PACK_OPENING,
                            BattlePhase.NEW_UNIT_UNLOCKED,
                        }
                    ),
                    {
                        "boost_slot": slot,
                        "spending_currency": "mastery_currency",
                        "bounded_once_per_slot": True,
                    },
                )
            return _Intent(
                ActionName.CONTINUE_MASTERY,
                (0.50, 0.84),
                frozenset(
                    {
                        BattlePhase.BIT_PACK_OPENING,
                        BattlePhase.NEW_UNIT_UNLOCKED,
                        BattlePhase.LEAGUE_MENU,
                        BattlePhase.HOME,
                    }
                ),
                {"boosts_attempted": tuple(sorted(self._boost_attempted_slots))},
            )
        if phase is BattlePhase.BIT_PACK_OPENING and not self._bit_pack_tapped:
            return _Intent(
                ActionName.SKIP_BIT_PACK,
                (0.50, 0.50),
                frozenset(
                    {
                        BattlePhase.NEW_UNIT_UNLOCKED,
                        BattlePhase.MASTERY_BOOST,
                        BattlePhase.LEAGUE_MENU,
                        BattlePhase.HOME,
                    }
                ),
                {"set_flag": "bit_pack_tapped"},
            )
        if phase is BattlePhase.NEW_UNIT_UNLOCKED:
            return _Intent(
                ActionName.CONTINUE_NEW_UNIT,
                (0.50, 0.78),
                frozenset(
                    {
                        BattlePhase.MASTERY_BOOST,
                        BattlePhase.LEAGUE_MENU,
                        BattlePhase.POST_BATTLE_OFFER,
                        BattlePhase.HOME,
                    }
                ),
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
        self._publish_automation(
            "action_issued",
            action=intent.name.value,
            command_id=command.command_id,
            point=command.point.as_tuple(),
            phase=phase.value,
            metadata=dict(intent.metadata),
        )
        logger.info("ACTION {} at {} from {}", intent.name.value, command.point.as_tuple(), phase.value)
        return pending

    def _resolved(
        self,
        pending: _Pending,
        phase: BattlePhase,
        frame: Frame,
        observation: Mapping[str, Any],
    ) -> bool:
        if phase not in pending.intent.success_phases:
            return False
        if (
            pending.intent.name is ActionName.PICK_DRAFT
            and phase in {BattlePhase.DRAFT_PICK, BattlePhase.RECOVERY_BONUS}
        ):
            before = pending.intent.metadata.get("draft_fingerprint", ())
            after = self._draft_fingerprint(observation.get("draft_choices", ()))
            return bool(before and after and after != before)
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
                if self._events is not None:
                    try:
                        self._events.publish(
                            RuntimeEvent(EventKind.OBSERVATION, self._clock(), observation)
                        )
                    except Exception:
                        pass
                if self._recovery is not None:
                    try:
                        recovery_result = self._recovery.after_observation(observation)
                        if recovery_result is not None and self._events is not None:
                            self._events.publish(
                                RuntimeEvent(
                                    EventKind.RECOVERY,
                                    self._clock(),
                                    dict(recovery_result),
                                )
                            )
                    except Exception as recovery_error:
                        self._publish_automation(
                            "recovery_error",
                            error=repr(recovery_error),
                            phase=phase.value,
                        )
                if self._recorder is not None:
                    self._recorder.record(frame, observation)

                if phase is last_phase:
                    stable_count += 1
                else:
                    last_phase = phase
                    stable_count = 1
                    self._publish_automation(
                        "phase_changed",
                        phase=phase.value,
                        frame_id=frame.id,
                        confidence=float(observation.get("confidence", 0.0)),
                    )
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
                    BattlePhase.DEFEAT_DISTRIBUTION,
                    BattlePhase.VICTORY_PACKAGE_READY,
                    BattlePhase.VICTORY_PACKAGE_ANIMATING,
                    BattlePhase.DOUBLE_BITS,
                    BattlePhase.MASTERY_BOOST,
                    BattlePhase.BIT_PACK_OPENING,
                    BattlePhase.NEW_UNIT_UNLOCKED,
                    BattlePhase.WATCHING_AD,
                    BattlePhase.AD_REWARD_GRANTED,
                    BattlePhase.LEAGUE_MENU,
                }:
                    battle_finished = battle_seen or battle_finished

                if pending is not None:
                    if self._resolved(pending, phase, frame, observation):
                        selected_unit = pending.intent.metadata.get("selected_unit")
                        if pending.intent.name is ActionName.PICK_DRAFT and selected_unit:
                            observed_unit = str(selected_unit)
                            resolved_unit = unit_for(observed_unit)
                            unit = (
                                resolved_unit.internal_name
                                if resolved_unit is not None
                                else observed_unit
                            )
                            current = self._draft_history.get(unit, 0)
                            effect = str(pending.intent.metadata.get("selected_effect") or "unknown")
                            magnitude = int(pending.intent.metadata.get("selected_magnitude") or 1)
                            initial_spawn = int(
                                pending.intent.metadata.get("selected_initial_spawn") or 1
                            )
                            if effect == "add":
                                self._draft_history[unit] = current + magnitude
                            elif effect == "multiply":
                                self._draft_history[unit] = (
                                    current * magnitude
                                    if current
                                    else initial_spawn * magnitude
                                )
                            else:
                                self._draft_history[unit] = max(initial_spawn, current)
                                if effect in {"upgrade", "transform"}:
                                    self._draft_tiers[unit] = min(
                                        3,
                                        self._draft_tiers.get(unit, 1) + 1,
                                    )
                        flag = pending.intent.metadata.get("set_flag")
                        if flag == "victory_reward_claimed":
                            self._victory_reward_claimed = True
                        elif flag == "double_bits_claimed":
                            self._double_bits_claimed = True
                        elif flag == "bit_pack_tapped":
                            self._bit_pack_tapped = True
                        boost_slot = pending.intent.metadata.get("boost_slot")
                        if type(boost_slot) is int:
                            self._boost_attempted_slots.add(boost_slot)
                        self._audit(
                            {
                                "event": "resolved",
                                "command_id": pending.command.command_id,
                                "action": pending.intent.name.value,
                                "frame_id": frame.id,
                                "phase": phase.value,
                            }
                        )
                        self._publish_automation(
                            "action_resolved",
                            action=pending.intent.name.value,
                            command_id=pending.command.command_id,
                            phase=phase.value,
                            frame_id=frame.id,
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
                        self._publish_automation(
                            "action_timeout",
                            action=pending.intent.name.value,
                            command_id=pending.command.command_id,
                            phase=phase.value,
                        )
                        raise ActionPostconditionTimeout(
                            f"{pending.intent.name.value} did not reach a visual postcondition"
                        )
                    self._cancellation.wait(self._settings.poll_interval_seconds)
                    continue

                if phase is BattlePhase.HOME and battle_finished:
                    self._publish_automation(
                        "completed",
                        phase=phase.value,
                        frames=frames,
                        actions=actions,
                    )
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
