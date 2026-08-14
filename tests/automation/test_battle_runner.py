from __future__ import annotations

import numpy as np
import pytest

from src.automation.battle_runner import (
    ActionName,
    ActionPostconditionTimeout,
    BattlePhase,
    BattleRunner,
    BattleSettings,
)
from src.capture.models import CaptureBackend, Frame
from src.core.cancellation import CancellationToken
from src.geometry.models import Size
from src.input.models import InputReceipt, InputStatus, TapCommand


def observation(screen: str, **extra: object) -> dict[str, object]:
    return {"screen": screen, "confidence": 0.99, "sub_element": screen.lower(), **extra}


class ScriptedCapture:
    def __init__(self, count: int) -> None:
        self.count = count
        self.index = 0
        self.generation = 0
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def invalidate_after_input(self) -> int:
        self.generation += 1
        return self.generation

    def next_frame(self, _request) -> Frame:
        if self.index >= self.count:
            raise AssertionError("scripted frames exhausted")
        self.index += 1
        image = np.full((1280, 720, 3), self.index % 255, dtype=np.uint8)
        return Frame(
            id=self.index,
            image=image,
            captured_at_monotonic=float(self.index),
            device_serial="test-device",
            backend=CaptureBackend.REPLAY,
            size=Size(720, 1280),
            connection_generation=0,
            capture_generation=self.generation,
        )


class ScriptedPerception:
    def __init__(self, observations: list[dict[str, object]]) -> None:
        self.observations = iter(observations)

    def analyze(self, _image, *, cancellation=None):
        return next(self.observations)


class RecordingInput:
    def __init__(self) -> None:
        self.commands: list[TapCommand] = []

    def execute(self, command: TapCommand) -> InputReceipt:
        self.commands.append(command)
        index = float(len(self.commands))
        return InputReceipt(command.command_id, InputStatus.SENT, "fake", index, index)


class RecordingRecorder:
    def __init__(self) -> None:
        self.frames: list[int] = []
        self.actions: list[dict[str, object]] = []
        self.closed = False

    def record(self, frame, _observation) -> None:
        self.frames.append(frame.id)

    def record_action(self, payload) -> None:
        self.actions.append(dict(payload))

    def close(self) -> None:
        self.closed = True


def test_one_battle_waits_for_postconditions_and_closes_paid_offer() -> None:
    observations = [
        observation("HOME"),
        observation("HOME"),
        observation("WAIT_MATCHMAKING"),
        observation("WAIT_MATCHMAKING"),
        observation("DRAFT_SCREEN", draft_available_slots=(1, 2), draft_variant="normal_pick"),
        observation("DRAFT_SCREEN", draft_available_slots=(1, 2), draft_variant="normal_pick"),
        observation("COMBAT"),
        observation("COMBAT"),
        observation("ROUND_RESULT"),
        observation("VICTORY_SUMMARY", victory_phase="splash"),
        observation("VICTORY_SUMMARY", victory_phase="splash"),
        observation("VICTORY_SUMMARY", victory_phase="mastery_distribution"),
        observation("VICTORY_SUMMARY", victory_phase="mastery_distribution"),
        observation("VICTORY_SUMMARY", victory_phase="package_ready", continue_visible=True),
        observation("VICTORY_SUMMARY", victory_phase="package_ready", continue_visible=True),
        observation("VICTORY_SUMMARY", victory_phase="package_animating", continue_visible=False),
        observation(
            "POST_BATTLE_OFFER",
            offer_close_visible=True,
            offer_close_point=(616 / 720, 432 / 1280),
        ),
        observation(
            "POST_BATTLE_OFFER",
            offer_close_visible=True,
            offer_close_point=(616 / 720, 432 / 1280),
        ),
        observation("HOME"),
        observation("HOME"),
    ]
    capture = ScriptedCapture(len(observations))
    input_backend = RecordingInput()
    recorder = RecordingRecorder()
    runner = BattleRunner(
        capture=capture,
        perception=ScriptedPerception(observations),
        input_backend=input_backend,
        cancellation=CancellationToken(),
        settings=BattleSettings(0, 0, stable_observations=2),
        recorder=recorder,
        clock=lambda: 1.0,
    )

    result = runner.run()

    assert result.completed is True
    assert result.final_phase is BattlePhase.HOME
    assert [command.command_id.split("-", 3)[-1] for command in input_backend.commands] == [
        "start_battle",
        "pick_draft",
        "skip_victory",
        "skip_mastery",
        "continue_victory",
        "close_offer",
    ]
    # Unreadable candidates tie deterministically; slot 1 wins, never blank slot 0.
    assert input_backend.commands[1].point.x == round(0.500 * 719)
    assert input_backend.commands[-1].point.y < 1280 // 2
    assert len([event for event in recorder.actions if event["event"] == "issued"]) == 6
    assert len([event for event in recorder.actions if event["event"] == "resolved"]) == 6
    assert capture.stopped is True
    assert recorder.closed is True


def test_passive_states_never_issue_actions() -> None:
    for phase in (
        BattlePhase.WAIT_MATCHMAKING,
        BattlePhase.COMBAT,
        BattlePhase.ROUND_RESULT,
        BattlePhase.VICTORY_PACKAGE_ANIMATING,
        BattlePhase.UNKNOWN,
        BattlePhase.WATCHING_AD,
    ):
        assert BattleRunner.__new__(BattleRunner)._intent(phase, {}) is None


def test_post_battle_rewards_boosts_and_ads_are_bounded_and_explicit() -> None:
    runner = BattleRunner.__new__(BattleRunner)
    runner._victory_reward_claimed = False
    runner._double_bits_claimed = False
    runner._boost_attempted_slots = set()
    runner._bit_pack_tapped = False

    victory = runner._intent(
        BattlePhase.VICTORY_PACKAGE_READY,
        {"reward_ad_available": True, "continue_visible": True},
    )
    assert victory is not None and victory.name is ActionName.CLAIM_VICTORY_AD

    assert runner._intent(BattlePhase.WATCHING_AD, {"safe_to_close": False}) is None
    close = runner._intent(
        BattlePhase.AD_REWARD_GRANTED,
        {"safe_to_close": True, "ad_close_point": (0.94, 0.04)},
    )
    assert close is not None and close.name is ActionName.CLOSE_REWARDED_AD

    double = runner._intent(
        BattlePhase.DOUBLE_BITS,
        {"double_bits_ad_available": True},
    )
    assert double is not None and double.name is ActionName.CLAIM_DOUBLE_BITS_AD
    runner._double_bits_claimed = True
    continued = runner._intent(BattlePhase.DOUBLE_BITS, {})
    assert continued is not None and continued.name is ActionName.CONTINUE_DOUBLE_BITS

    boost = runner._intent(
        BattlePhase.MASTERY_BOOST,
        {"boost_available_slots": (0, 1, 2, 3), "resources": {"mastery_currency": 15}},
    )
    assert boost is not None and boost.name is ActionName.APPLY_MASTERY_BOOST
    assert boost.metadata["boost_slot"] == 0
    runner._boost_attempted_slots = {0, 1, 2, 3}
    finish_boost = runner._intent(BattlePhase.MASTERY_BOOST, {"boost_available_slots": (0, 1, 2, 3)})
    assert finish_boost is not None and finish_boost.name is ActionName.CONTINUE_MASTERY


def test_mastery_boost_does_not_spend_when_known_currency_is_empty() -> None:
    runner = BattleRunner.__new__(BattleRunner)
    runner._boost_attempted_slots = set()
    intent = runner._intent(
        BattlePhase.MASTERY_BOOST,
        {"boost_available_slots": (0, 1), "resources": {"mastery_currency": 0}},
    )
    assert intent is not None and intent.name is ActionName.CONTINUE_MASTERY


def test_missing_postcondition_stops_without_repeating_tap() -> None:
    observations = [observation("HOME") for _ in range(8)]
    capture = ScriptedCapture(len(observations))
    input_backend = RecordingInput()
    ticks = iter(index * 0.1 for index in range(100))
    runner = BattleRunner(
        capture=capture,
        perception=ScriptedPerception(observations),
        input_backend=input_backend,
        cancellation=CancellationToken(),
        settings=BattleSettings(0, 0, stable_observations=2, postcondition_timeout_seconds=0.15),
        clock=ticks.__next__,
    )

    with pytest.raises(ActionPostconditionTimeout):
        runner.run()

    assert len(input_backend.commands) == 1
    assert capture.stopped is True
