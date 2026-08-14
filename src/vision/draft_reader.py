from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from src.vision.ocr_engine import shared_rapidocr


_KNOWN_UNITS = (
    "Cavaleiro",
    "Cupido",
    "Ganso",
    "Engenheiro",
    "TNT",
    "Caracol",
    "Assassino",
    "Splime",
    "Reiclops",
)


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character)).casefold()


@dataclass(frozen=True, slots=True)
class DraftCard:
    slot: int
    text: str
    unit: str | None
    effect: str
    magnitude: int
    confidence: float

    def payload(self) -> dict[str, object]:
        return {
            "slot": self.slot,
            "text": self.text,
            "unit": self.unit,
            "effect": self.effect,
            "magnitude": self.magnitude,
            "confidence": round(self.confidence, 4),
        }


class DraftCardReader:
    """Convert the visible text on each available draft card into facts."""

    def __init__(self, *, engine_factory: Callable[[], Any] | None = None) -> None:
        self._engine_factory = engine_factory or self._default_engine_factory
        self._engine: Any | None = None
        self._slot_cache: dict[int, tuple[np.ndarray, DraftCard]] = {}

    @staticmethod
    def _default_engine_factory() -> Any:
        return shared_rapidocr()

    @property
    def _ocr(self) -> Any:
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine

    @staticmethod
    def _region(frame: np.ndarray, slot: int) -> np.ndarray:
        height, width = frame.shape[:2]
        bounds = ((0.00, 0.34), (0.33, 0.67), (0.66, 1.00))[slot]
        return frame[
            round(height * 0.40) : round(height * 0.72),
            round(width * bounds[0]) : round(width * bounds[1]),
        ]

    @staticmethod
    def _parse(slot: int, texts: Iterable[str], scores: Iterable[float]) -> DraftCard:
        accepted = [
            (str(text).strip(), float(score))
            for text, score in zip(texts, scores, strict=False)
            if str(text).strip() and float(score) >= 0.62
        ]
        descriptive = [(text, score) for text, score in accepted if re.search(r"[A-Za-zÀ-ÿ]", text)]
        description = " ".join(text for text, _score in descriptive).strip()
        normalized = _normalized(description)
        unit = next(
            (known for known in _KNOWN_UNITS if _normalized(known) in normalized),
            None,
        )
        effect = "unknown"
        magnitude = 1
        added = re.search(r"\+\s*(\d+)", normalized)
        multiplied = re.search(r"x\s*(\d+)", normalized)
        if added is not None:
            effect = "add"
            magnitude = int(added.group(1))
        elif multiplied is not None:
            effect = "multiply"
            magnitude = int(multiplied.group(1))
        elif "up" in normalized or "zumbi" in normalized:
            effect = "upgrade"
        confidence = (
            sum(score for _text, score in descriptive) / len(descriptive)
            if descriptive
            else 0.0
        )
        return DraftCard(slot, description or "OCR_UNREADABLE", unit, effect, magnitude, confidence)

    def read(self, frame: np.ndarray, available_slots: Iterable[int]) -> tuple[DraftCard, ...]:
        cards: list[DraftCard] = []
        for slot in available_slots:
            if type(slot) is not int or not 0 <= slot <= 2:
                continue
            region = self._region(frame, slot)
            signature = cv2.resize(
                cv2.cvtColor(region, cv2.COLOR_BGR2GRAY),
                (32, 32),
                interpolation=cv2.INTER_AREA,
            )
            cached = self._slot_cache.get(slot)
            if cached is not None:
                previous_signature, previous_card = cached
                visual_delta = float(
                    np.mean(cv2.absdiff(signature, previous_signature))
                )
                if visual_delta < 2.5:
                    cards.append(previous_card)
                    continue
            try:
                # RapidOCR keeps per-call mode overrides on the engine instance.
                # ResourceReader deliberately disables detection for tiny fixed
                # fields, so every full-image consumer must restore all stages.
                result = self._ocr(
                    region,
                    use_det=True,
                    use_cls=True,
                    use_rec=True,
                )
                texts = getattr(result, "txts", ()) if result is not None else ()
                scores = getattr(result, "scores", ()) if result is not None else ()
            except Exception:
                texts, scores = (), ()
            card = self._parse(slot, texts or (), scores or ())
            self._slot_cache[slot] = (signature, card)
            cards.append(card)
        return tuple(cards)
