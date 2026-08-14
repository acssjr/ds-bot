from pathlib import Path

import cv2
import pytest

from src.state.game_state import ScreenState
from src.vision.pipeline import VisionPipeline


SCREENSHOTS = Path(__file__).resolve().parents[2] / "screenshots"
NAVIGATION = Path(__file__).resolve().parents[1] / "fixtures" / "navigation_session"


@pytest.fixture(scope="module")
def pipeline() -> VisionPipeline:
    return VisionPipeline()


@pytest.mark.parametrize(
    ("filename", "screen", "element"),
    [
        ("tela vitoria 2 reinvindicar bonus ads.png", ScreenState.VICTORY_SUMMARY, "ocr:victory_reward_available"),
        ("anuncio-indisponivel.png", ScreenState.VICTORY_SUMMARY, "ocr:victory_reward_cooldown"),
        ("dobro-bits-pos-reinvindicar.png", ScreenState.DOUBLE_BITS, "ocr:x2_bits"),
        ("impulso.png", ScreenState.MASTERY_BOOST, "ocr:mastery_boost"),
        ("bit-pack.png", ScreenState.BIT_PACK_OPENING, "ocr:bit_pack"),
        ("nova-unidade.png", ScreenState.NEW_UNIT_UNLOCKED, "ocr:new_unit"),
    ],
)
def test_manual_flow_examples_are_distinct_evidence_not_templates(
    filename, screen, element, pipeline: VisionPipeline
) -> None:
    frame = cv2.imread(str(SCREENSHOTS / filename), cv2.IMREAD_COLOR)
    assert frame is not None
    result = pipeline.analyze(frame)
    assert result["screen"] is screen
    assert result["sub_element"] == element


def test_ad_close_is_exposed_only_after_reward_completion(pipeline: VisionPipeline) -> None:
    pending = pipeline.analyze(cv2.imread(str(NAVIGATION / "ad_progress.jpg")))
    ready = pipeline.analyze(cv2.imread(str(NAVIGATION / "ad_close_ready.jpg")))
    granted = pipeline.analyze(cv2.imread(str(NAVIGATION / "ad_reward_granted.jpg")))

    assert pending["screen"] is ScreenState.WATCHING_AD
    assert pending["safe_to_close"] is False
    assert ready["safe_to_close"] is True
    assert ready["ad_close_point"][0] > 0.9
    assert granted["safe_to_close"] is True
    assert granted["ad_close_point"][0] < 0.1
