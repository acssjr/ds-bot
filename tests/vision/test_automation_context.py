from pathlib import Path

import cv2
import pytest

from src.state.game_state import ScreenState
from src.vision.pipeline import VisionPipeline


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live_session"


def _analyze(filename: str) -> dict:
    frame = cv2.imread(str(FIXTURES / filename), cv2.IMREAD_COLOR)
    assert frame is not None
    return VisionPipeline().analyze(frame)


@pytest.mark.parametrize(
    ("filename", "slots", "variant"),
    [
        ("draft_left_empty.jpg", (1, 2), "normal_pick"),
        ("draft_middle_empty.jpg", (0, 2), "normal_pick"),
        ("draft_recovery.jpg", (0, 1, 2), "recovery_bonus"),
    ],
)
def test_draft_context_maps_only_visually_available_slots(filename, slots, variant) -> None:
    result = _analyze(filename)

    assert result["screen"] is ScreenState.DRAFT_SCREEN
    assert result["draft_available_slots"] == slots
    assert result["draft_variant"] == variant


@pytest.mark.parametrize(
    ("filename", "phase", "continue_visible"),
    [
        ("victory_splash.jpg", "splash", False),
        ("victory_mastery.jpg", "mastery_distribution", False),
        ("victory_package_ready.jpg", "package_ready", True),
        ("victory_package_animating.jpg", "package_animating", False),
    ],
)
def test_victory_context_separates_actionable_phases(filename, phase, continue_visible) -> None:
    result = _analyze(filename)

    assert result["screen"] is ScreenState.VICTORY_SUMMARY
    assert result["victory_phase"] == phase
    assert result["continue_visible"] is continue_visible


def test_paid_post_battle_offer_exposes_only_safe_close_target() -> None:
    result = _analyze("post_battle_offer.jpg")

    assert result["screen"] is ScreenState.POST_BATTLE_OFFER
    assert result["context"] == "post_battle_offer"
    assert result["purchase_allowed"] is False
    assert result["offer_close_visible"] is True
    x, y = result["offer_close_point"]
    assert x == pytest.approx(616 / 720, abs=0.01)
    assert y == pytest.approx(432 / 1280, abs=0.01)


def test_matchmaking_red_background_is_not_a_post_battle_offer() -> None:
    result = _analyze("matchmaking.jpg")

    assert result["screen"] is ScreenState.WAIT_MATCHMAKING
    assert result.get("offer_close_visible") is not True
