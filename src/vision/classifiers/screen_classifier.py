import os
import cv2
import numpy as np
from loguru import logger
from typing import Dict, Tuple, Optional, Any

from src.state.game_state import ScreenState
from src.utils.coordinates import CoordinateConverter

class ScreenClassifier:
    """
    Classifica a tela atual (ScreenState) comparando os 20 templates extraídos dos screenshots.
    """

    def __init__(self, templates_dir: str = "assets/templates"):
        self.templates_dir = templates_dir
        # Mapeamento de pasta de template -> ScreenState
        self.folder_to_state: Dict[str, ScreenState] = {
            "home": ScreenState.HOME,
            "wait_matchmaking": ScreenState.WAIT_MATCHMAKING,
            "draft_screen": ScreenState.DRAFT_SCREEN,
            "victory_summary": ScreenState.VICTORY_SUMMARY,
            "double_bits": ScreenState.DOUBLE_BITS,
            "mastery_boost": ScreenState.MASTERY_BOOST,
            "bit_pack": ScreenState.BIT_PACK_OPENING,
            "new_unit": ScreenState.NEW_UNIT_UNLOCKED,
            "watching_ad": ScreenState.WATCHING_AD,
            "collection_menu": ScreenState.COLLECTION_MENU,
        }
        self.templates: Dict[ScreenState, list] = {}
        self.threshold = 0.70
        self._load_templates()

    def _load_templates(self) -> None:
        """Carrega todos os arquivos .png salvos no diretório assets/templates/."""
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir, exist_ok=True)
            return

        for folder, state in self.folder_to_state.items():
            folder_path = os.path.join(self.templates_dir, folder)
            if os.path.exists(folder_path):
                if state not in self.templates:
                    self.templates[state] = []
                for fname in os.listdir(folder_path):
                    if fname.endswith((".png", ".jpg")):
                        fpath = os.path.join(folder_path, fname)
                        tpl = cv2.imread(fpath, cv2.IMREAD_COLOR)
                        if tpl is not None:
                            self.templates[state].append((fname, tpl))
                            logger.debug(f"Template carregado [{state.value}]: {fname}")

    def classify(self, frame: np.ndarray) -> Tuple[ScreenState, float, Optional[str]]:
        """
        Analisa o frame e retorna (ScreenState, confidence, sub_element_name).
        """
        if frame is None:
            return (ScreenState.UNKNOWN, 0.0, None)

        best_state = ScreenState.UNKNOWN
        best_val = 0.0
        best_sub_element = None

        for state, tpl_list in self.templates.items():
            for fname, tpl in tpl_list:
                if frame.shape[0] < tpl.shape[0] or frame.shape[1] < tpl.shape[1]:
                    continue

                res = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)

                if max_val > best_val and max_val >= self.threshold:
                    best_val = max_val
                    best_state = state
                    best_sub_element = fname.replace(".png", "")

        return (best_state, best_val, best_sub_element)
