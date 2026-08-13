import numpy as np
from loguru import logger
from typing import Dict, Any

from src.vision.classifiers.screen_classifier import ScreenClassifier
from src.state.game_state import ScreenState

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
            }

        screen_state, confidence, sub_element = self.screen_classifier.classify(frame)

        return {
            "screen": screen_state,
            "confidence": confidence,
            "sub_element": sub_element,
            "frame_shape": frame.shape
        }
