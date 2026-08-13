import numpy as np

from src.actions.action_model import ActionType
from src.actions.action_planner import ActionPlanner
from src.state.game_state import ScreenState
from src.state.state_manager import StateManager
from src.utils.coordinates import CoordinateConverter
from src.vision.pipeline import VisionPipeline


def test_coordinate_round_trip() -> None:
    normalized = CoordinateConverter.normalize(640, 360, 1280, 720)

    assert CoordinateConverter.denormalize(*normalized, 1280, 720) == (640, 360)


def test_legacy_fsm_requires_two_matching_observations() -> None:
    manager = StateManager(persistence_frames=2)
    observation = {
        "screen": ScreenState.HOME,
        "confidence": 0.9,
        "sub_element": "battle",
    }

    assert manager.update(observation).screen is ScreenState.UNKNOWN
    assert manager.update(observation).screen is ScreenState.HOME


def test_legacy_vision_returns_unknown_without_fabricated_choices() -> None:
    result = VisionPipeline(templates_dir="assets/templates").analyze(
        np.zeros((720, 1280, 3), dtype=np.uint8)
    )

    assert result["screen"] is ScreenState.UNKNOWN
    assert result["confidence"] == 0.0
    assert "available_choices" not in result


def test_reward_policy_keeps_existing_user_choice() -> None:
    action = ActionPlanner().plan_handle_victory_summary(
        sub_element="timer_ad_btn",
        watch_ads=True,
    )

    assert action.action_type is ActionType.TAP
    assert action.normalized_start == ActionPlanner.POSITIONS["CONTINUAR_BROWN_BTN"]
    assert "Continuar" in action.metadata
