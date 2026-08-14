from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Any

import numpy as np

from src.state.game_state import ScreenState
from src.vision.ocr_engine import shared_rapidocr


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).upper()


class FlowScreenReader:
    """OCR fallback for distinctive post-battle screens.

    It is invoked only after fast template/color classification returns UNKNOWN.
    """

    def __init__(self, *, engine_factory: Callable[[], Any] | None = None) -> None:
        self._engine_factory = engine_factory or self._default_engine_factory
        self._engine: Any | None = None

    @staticmethod
    def _default_engine_factory() -> Any:
        return shared_rapidocr()

    @property
    def _ocr(self) -> Any:
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine

    def classify(self, frame: np.ndarray) -> tuple[ScreenState, float, str | None]:
        try:
            result = self._ocr(frame)
        except Exception:
            return ScreenState.UNKNOWN, 0.0, None
        if result is None:
            return ScreenState.UNKNOWN, 0.0, None
        tokens = [
            _normalized(str(text).strip())
            for text, score in zip(result.txts or (), result.scores or (), strict=False)
            if str(text).strip() and float(score) >= 0.62
        ]
        joined = " | ".join(tokens)
        impulso_count = sum("IMPULSO" in token for token in tokens)
        if "X2 BITS" in joined and "CONTINUAR" in joined:
            return ScreenState.DOUBLE_BITS, 0.94, "ocr:x2_bits"
        if impulso_count >= 2 and "CONTINUAR" in joined:
            return ScreenState.MASTERY_BOOST, 0.94, "ocr:mastery_boost"
        if "TOQUE PARA PULAR" in joined and ("PACK" in joined or "BIT" in joined):
            return ScreenState.BIT_PACK_OPENING, 0.95, "ocr:bit_pack"
        if "NOVA UNIDADE" in joined and "CONTINUAR" in joined:
            return ScreenState.NEW_UNIT_UNLOCKED, 0.95, "ocr:new_unit"
        victory = "VITORIA" in joined and "PACOTE DE VITORIA" in joined
        if victory and "REIV." in joined and "CONTINUAR" in joined:
            return ScreenState.VICTORY_SUMMARY, 0.94, "ocr:victory_reward_available"
        if victory and "TEMPO RESTANTE" in joined and "CONTINUAR" in joined:
            return ScreenState.VICTORY_SUMMARY, 0.94, "ocr:victory_reward_cooldown"
        return ScreenState.UNKNOWN, 0.0, None
