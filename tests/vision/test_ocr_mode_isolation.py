from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from src.state.game_state import ScreenState
from src.vision.draft_reader import DraftCardReader
from src.vision.flow_screen_reader import FlowScreenReader


class StatefulEngine:
    """Model the RapidOCR per-call mode persistence that caused the live bug."""

    def __init__(self, texts: tuple[str, ...]) -> None:
        self.mode = {"use_det": False, "use_cls": False, "use_rec": True}
        self.texts = texts
        self.calls: list[dict[str, object]] = []

    def __call__(self, _image: np.ndarray, **kwargs: object) -> object:
        self.mode.update(kwargs)
        self.calls.append(dict(kwargs))
        if self.mode != {"use_det": True, "use_cls": True, "use_rec": True}:
            return SimpleNamespace(txts=("unreadable",), scores=(0.1,))
        return SimpleNamespace(txts=self.texts, scores=(1.0,) * len(self.texts))


def test_draft_reader_restores_full_ocr_after_resource_crop_mode() -> None:
    engine = StatefulEngine(("+3 Cavaleiro",))
    reader = DraftCardReader(engine_factory=lambda: engine)

    cards = reader.read(np.zeros((1280, 720, 3), dtype=np.uint8), (0,))

    assert cards[0].unit == "Cavaleiro"
    assert cards[0].magnitude == 3
    assert engine.calls == [{"use_det": True, "use_cls": True, "use_rec": True}]


def test_defeat_reader_restores_full_ocr_and_names_both_defeat_phases() -> None:
    frame = np.zeros((1280, 720, 3), dtype=np.uint8)
    distribution_engine = StatefulEngine(("DERROTA", "TOQUE PARA PULAR"))
    distribution = FlowScreenReader(engine_factory=lambda: distribution_engine)
    boost_engine = StatefulEngine(
        ("DERROTA", "IMPULSO", "IMPULSO", "IMPULSO", "CONTINUAR")
    )
    boost = FlowScreenReader(engine_factory=lambda: boost_engine)

    assert distribution.classify(frame) == (
        ScreenState.DEFEAT_SUMMARY,
        0.95,
        "ocr:defeat_distribution",
    )
    assert boost.classify(frame) == (
        ScreenState.MASTERY_BOOST,
        0.94,
        "ocr:defeat_mastery_boost",
    )
