from pathlib import Path

import cv2
import pytest

from src.state.game_state import ScreenState
from src.vision.classifiers.screen_classifier import ScreenClassifier
from src.vision.pipeline import VisionPipeline


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "navigation_session"


def _image(filename: str):
    image = cv2.imread(str(FIXTURES / filename), cv2.IMREAD_COLOR)
    assert image is not None
    return image


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("shop.jpg", ScreenState.SHOP_MENU),
        ("daily_offers.jpg", ScreenState.SHOP_DAILY_OFFERS),
        ("ad_countdown.jpg", ScreenState.WATCHING_AD),
        ("ad_progress.jpg", ScreenState.WATCHING_AD),
        ("ad_close_ready.jpg", ScreenState.AD_REWARD_GRANTED),
        ("ad_reward_granted.jpg", ScreenState.AD_REWARD_GRANTED),
        ("league.jpg", ScreenState.LEAGUE_MENU),
        ("ranked_locked.jpg", ScreenState.RANKED_LOCKED),
        ("profile.jpg", ScreenState.PROFILE_MENU),
    ],
)
def test_recognizes_shop_ads_and_league_from_live_navigation(
    filename: str, expected: ScreenState
) -> None:
    screen, confidence, sub_element = ScreenClassifier().classify(_image(filename))

    assert screen is expected
    assert confidence >= 0.72
    assert sub_element


def test_rewarded_ad_never_reports_safe_close_before_visual_completion() -> None:
    pipeline = VisionPipeline()

    pending = pipeline.analyze(_image("ad_countdown.jpg"))
    carried = pipeline.analyze(_image("ad_middle.jpg"))
    granted = pipeline.analyze(_image("ad_close_ready.jpg"))

    assert pending["screen"] is ScreenState.WATCHING_AD
    assert pending["safe_to_close"] is False
    assert carried["screen"] is ScreenState.WATCHING_AD
    assert carried["safe_to_close"] is False
    assert granted["screen"] is ScreenState.AD_REWARD_GRANTED
    assert granted["safe_to_close"] is True


def test_daily_offers_expose_only_visible_availability_facts() -> None:
    result = VisionPipeline().analyze(_image("daily_offers.jpg"))

    assert result["screen"] is ScreenState.SHOP_DAILY_OFFERS
    assert result["free_ad_offers_visible"] == 2
    assert result["daily_refresh_ad_visible"] is True
    assert result["next_refresh_countdown_visible"] is True
    assert result["next_refresh_text"] == "OCR_PENDING"
