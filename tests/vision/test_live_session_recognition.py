from pathlib import Path

import cv2
import pytest

from src.state.game_state import ScreenState
from src.vision.classifiers.screen_classifier import ScreenClassifier


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live_session"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("home.jpg", ScreenState.HOME),
        ("collection.jpg", ScreenState.COLLECTION_MENU),
        ("matchmaking.jpg", ScreenState.WAIT_MATCHMAKING),
        ("match_intro.jpg", ScreenState.WAIT_MATCHMAKING),
        ("draft.jpg", ScreenState.DRAFT_SCREEN),
        ("combat.jpg", ScreenState.COMBAT),
        ("round_result.jpg", ScreenState.ROUND_RESULT),
        ("victory_intro.jpg", ScreenState.VICTORY_SUMMARY),
        ("victory_package.jpg", ScreenState.VICTORY_SUMMARY),
    ],
)
def test_recognizes_verified_stages_from_a_complete_live_match(
    filename: str, expected: ScreenState
) -> None:
    frame = cv2.imread(str(FIXTURES / filename), cv2.IMREAD_COLOR)
    assert frame is not None

    screen, confidence, sub_element = ScreenClassifier().classify(frame)

    assert screen is expected
    assert confidence >= 0.64
    assert sub_element
