import numpy as np
from loguru import logger
from typing import Dict, Any

from src.vision.classifiers.screen_classifier import ScreenClassifier
from src.state.game_state import ScreenState, CardChoice, CardRole

class VisionPipeline:
    """Orquestra a análise visual do frame combinando classificação de tela e sub-detectores."""

    def __init__(self, templates_dir: str = "assets/templates"):
        self.screen_classifier = ScreenClassifier(templates_dir=templates_dir)

    def analyze(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Executa o pipeline visual completo no frame e retorna um dicionário de percepção.
        """
        if frame is None:
            return {
                "screen": ScreenState.UNKNOWN,
                "confidence": 0.0,
                "sub_element": None,
                "available_choices": []
            }

        screen_state, confidence, sub_element = self.screen_classifier.classify(frame)

        choices = []
        if screen_state == ScreenState.DRAFT_SCREEN or screen_state == ScreenState.UNKNOWN:
            choices = [
                CardChoice(slot_index=0, name="Slot 0 Card", role=CardRole.TANK),
                CardChoice(slot_index=1, name="Slot 1 Card", role=CardRole.RANGED_DPS),
                CardChoice(slot_index=2, name="Slot 2 Card", role=CardRole.UTILITY)
            ]

        return {
            "screen": screen_state,
            "confidence": confidence,
            "sub_element": sub_element,
            "available_choices": choices,
            "frame_shape": frame.shape
        }
