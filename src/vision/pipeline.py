import numpy as np
from loguru import logger
from typing import Dict, Any

from src.vision.classifiers.screen_classifier import ScreenClassifier
from src.vision.context_analyzer import ContextAnalyzer
from src.core.cancellation import CancellationToken
from src.state.game_state import ScreenState
from src.vision.resource_reader import ResourceReader
from src.vision.flow_screen_reader import FlowScreenReader

class VisionPipeline:
    """Orquestra a análise visual do frame combinando classificação de tela e sub-detectores."""

    def __init__(
        self,
        templates_dir: str = "assets/templates",
        *,
        resource_reader: ResourceReader | None = None,
        flow_reader: FlowScreenReader | None = None,
    ):
        self.screen_classifier = ScreenClassifier(templates_dir=templates_dir)
        self.context_analyzer = ContextAnalyzer(templates_dir)
        self.flow_reader = flow_reader or FlowScreenReader()
        self._last_screen = ScreenState.UNKNOWN
        self._last_confidence = 0.0
        self._unknown_streak = 0
        self.resource_reader = resource_reader

    _STICKY_SCREENS = {
        ScreenState.SHOP_MENU,
        ScreenState.SHOP_DAILY_OFFERS,
        ScreenState.WATCHING_AD,
        ScreenState.AD_REWARD_GRANTED,
        ScreenState.LEAGUE_MENU,
        ScreenState.RANKED_LOCKED,
        ScreenState.PROFILE_MENU,
    }

    def analyze(self, frame: np.ndarray, *, cancellation: CancellationToken | None = None) -> Dict[str, Any]:
        """
        Executa o pipeline visual completo no frame e retorna um dicionário de percepção.
        """
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        if frame is None:
            return {
                "screen": ScreenState.UNKNOWN,
                "confidence": 0.0,
                "sub_element": None,
            }

        if cancellation is None:
            screen_state, confidence, sub_element = self.screen_classifier.classify(frame)
        else:
            screen_state, confidence, sub_element = self.screen_classifier.classify(frame, cancellation=cancellation)
        if cancellation is not None:
            cancellation.raise_if_cancelled()

        needs_flow_text = (
            screen_state is ScreenState.UNKNOWN and sub_element != "blank_frame"
        ) or (
            screen_state is ScreenState.VICTORY_SUMMARY
            and sub_element == "victory_package"
        )
        flow_reader = getattr(self, "flow_reader", None)
        if needs_flow_text and flow_reader is not None:
            fallback_screen, fallback_confidence, fallback_element = flow_reader.classify(frame)
            if fallback_screen is not ScreenState.UNKNOWN:
                screen_state = fallback_screen
                confidence = max(confidence, fallback_confidence)
                sub_element = fallback_element

        if (
            screen_state is ScreenState.UNKNOWN
            and sub_element != "blank_frame"
            and self._last_screen in self._STICKY_SCREENS
            and self._unknown_streak < 12
        ):
            self._unknown_streak += 1
            screen_state = self._last_screen
            confidence = max(0.51, self._last_confidence * (0.92 ** self._unknown_streak))
            sub_element = f"carried:{screen_state.value.lower()}"
        elif screen_state is not ScreenState.UNKNOWN:
            self._last_screen = screen_state
            self._last_confidence = confidence
            self._unknown_streak = 0
        else:
            self._unknown_streak += 1

        result = {
            "screen": screen_state,
            "confidence": confidence,
            "sub_element": sub_element,
            "frame_shape": frame.shape
        }
        result.update(self.context_analyzer.analyze(frame, screen_state, sub_element))
        resource_reader = getattr(self, "resource_reader", None)
        if resource_reader is not None:
            result.update(resource_reader.analyze(frame, screen_state))
        return result
