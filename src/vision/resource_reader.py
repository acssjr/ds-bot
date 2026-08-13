from __future__ import annotations

import re
import time
import json
from collections.abc import Callable
from difflib import SequenceMatcher
from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from src.state.game_state import ScreenState


_MENU_SCREENS = {
    ScreenState.HOME,
    ScreenState.COLLECTION_MENU,
    ScreenState.SHOP_MENU,
    ScreenState.SHOP_DAILY_OFFERS,
    ScreenState.LEAGUE_MENU,
    ScreenState.PROFILE_MENU,
}

_FIELD_ROIS = {
    "energy": (85, 25, 200, 78),
    "gems": (240, 25, 315, 78),
    "coins": (380, 25, 470, 78),
    "mastery_currency": (555, 25, 620, 78),
    "trophies": (60, 205, 145, 272),
    "player_level": (175, 220, 235, 272),
}

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


def _digits(text: str) -> int | None:
    cleaned = re.sub(r"[^0-9]", "", text)
    return int(cleaned) if cleaned else None


def _ratio(text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


class ResourceReader:
    """Reads stable account fields and retains the last trustworthy snapshot.

    Fast recognition is limited to fixed regions. Full-page OCR only runs when
    entering Collection or League (or after a long refresh interval).
    """

    def __init__(
        self,
        *,
        engine_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
        top_interval_seconds: float = 3.0,
        detail_interval_seconds: float = 30.0,
        state_path: str | PathLike[str] | None = None,
    ) -> None:
        self._engine_factory = engine_factory or self._default_engine_factory
        self._engine: Any | None = None
        self._clock = clock
        self._top_interval = top_interval_seconds
        self._detail_interval = detail_interval_seconds
        self._last_top_at = float("-inf")
        self._last_detail_at: dict[ScreenState, float] = {}
        self._last_screen = ScreenState.UNKNOWN
        self._state_path = Path(state_path) if state_path is not None else None
        self._snapshot: dict[str, Any] = self._load_snapshot()

    def _load_snapshot(self) -> dict[str, Any]:
        if self._state_path is None or not self._state_path.is_file():
            return {}
        try:
            loaded = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and all(isinstance(key, str) for key in loaded):
                return loaded
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("Stored resource snapshot is invalid; starting empty: {!r}", exc)
        return {}

    def _save_snapshot(self) -> None:
        if self._state_path is None:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self._snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self._state_path)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Could not persist resource snapshot: {!r}", exc)

    @staticmethod
    def _default_engine_factory() -> Any:
        from rapidocr import RapidOCR

        return RapidOCR()

    @property
    def _ocr(self) -> Any:
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine

    @staticmethod
    def _crop(frame: np.ndarray, roi: tuple[int, int, int, int]) -> np.ndarray:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = roi
        sx, sy = width / 720.0, height / 1280.0
        return frame[
            max(0, round(y1 * sy)) : min(height, round(y2 * sy)),
            max(0, round(x1 * sx)) : min(width, round(x2 * sx)),
        ]

    def _read_field(self, frame: np.ndarray, name: str) -> tuple[str, float] | None:
        result = self._ocr(
            self._crop(frame, _FIELD_ROIS[name]),
            use_det=False,
            use_cls=False,
            use_rec=True,
        )
        texts = tuple(getattr(result, "txts", ()) or ())
        scores = tuple(getattr(result, "scores", ()) or ())
        if not texts or not scores or float(scores[0]) < 0.80:
            return None
        return str(texts[0]), float(scores[0])

    def _read_top(self, frame: np.ndarray, screen: ScreenState) -> None:
        fields = ["energy", "gems", "coins", "mastery_currency"]
        if screen is ScreenState.HOME:
            fields += ["trophies", "player_level"]
        confidences: list[float] = []
        for name in fields:
            reading = self._read_field(frame, name)
            if reading is None:
                continue
            text, confidence = reading
            if name == "energy":
                value = _ratio(text)
                if value is not None:
                    self._snapshot["energy_current"], self._snapshot["energy_capacity"] = value
                    confidences.append(confidence)
            else:
                value = _digits(text)
                if value is not None:
                    self._snapshot[name] = value
                    confidences.append(confidence)
        if confidences:
            self._snapshot["resource_confidence"] = round(min(confidences), 4)

    @staticmethod
    def _items(result: Any) -> list[tuple[float, float, str, float]]:
        items: list[tuple[float, float, str, float]] = []
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or texts is None or scores is None:
            return items
        for box, text, score in zip(
            boxes,
            texts,
            scores,
        ):
            points = np.asarray(box, dtype=float)
            center = points.mean(axis=0)
            items.append((float(center[0]), float(center[1]), str(text), float(score)))
        return items

    @staticmethod
    def _canonical_unit(text: str) -> str | None:
        normalized = text.casefold()
        best = max(
            _KNOWN_UNITS,
            key=lambda candidate: SequenceMatcher(None, normalized, candidate.casefold()).ratio(),
        )
        similarity = SequenceMatcher(None, normalized, best.casefold()).ratio()
        return best if similarity >= 0.58 else None

    def _read_collection(self, result: Any) -> None:
        items = self._items(result)
        for _x, _y, text, _score in items:
            ratio = _ratio(text)
            if ratio is not None and "cole" not in text.casefold():
                current, total = ratio
                if total <= 100:
                    self._snapshot["collection_unlocked"] = current
                    self._snapshot["collection_total"] = total

        units: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for x, y, text, confidence in items:
            canonical = self._canonical_unit(text)
            if canonical is None or confidence < 0.55:
                continue
            numeric_candidates = [
                (abs(nx - x) + abs(ny - y), _digits(ntext), nscore)
                for nx, ny, ntext, nscore in items
                if abs(nx - x) < 75 and 15 < ny - y < 85 and _digits(ntext) is not None
            ]
            if not numeric_candidates:
                continue
            _distance, level, level_confidence = min(numeric_candidates, key=lambda item: item[0])
            if level is None or not 1 <= level <= 99:
                continue
            mastery_candidates = [
                (abs(nx - x) + abs(ny - y), _digits(ntext), nscore)
                for nx, ny, ntext, nscore in items
                if abs(nx - x) < 75 and 100 < y - ny < 220 and _digits(ntext) is not None
            ]
            key = (canonical, level)
            if key in seen:
                continue
            seen.add(key)
            unit = {
                "name": canonical,
                "level": level,
                "confidence": round(min(confidence, level_confidence), 4),
            }
            if mastery_candidates:
                _distance, mastery, mastery_confidence = min(
                    mastery_candidates,
                    key=lambda item: item[0],
                )
                if mastery is not None and 0 <= mastery <= 99:
                    unit["mastery"] = mastery
                    unit["confidence"] = round(
                        min(float(unit["confidence"]), mastery_confidence),
                        4,
                    )
            units.append(unit)
        if units:
            self._snapshot["units"] = tuple(units)

    def _read_league(self, result: Any) -> None:
        items = self._items(result)
        for _x, _y, text, _score in items:
            upper = text.upper()
            if upper.startswith("LIGA "):
                self._snapshot["league"] = text[5:].strip().title()
            if "TERMINA EM" in upper:
                self._snapshot["league_ends"] = text.split(":", 1)[-1].strip()

        player = next((item for item in items if "eupiroca" in item[2].casefold()), None)
        if player is None:
            return
        _player_x, player_y, _name, _score = player
        same_row = sorted(
            (
                (x, _digits(text))
                for x, y, text, _score in items
                if abs(y - player_y) < 35 and _digits(text) is not None
            ),
            key=lambda item: item[0],
        )
        if len(same_row) >= 2:
            self._snapshot["league_rank"] = same_row[0][1]
            self._snapshot["league_points"] = same_row[-1][1]

    def analyze(self, frame: np.ndarray, screen: ScreenState) -> dict[str, Any]:
        now = self._clock()
        snapshot_before = dict(self._snapshot)
        entered = screen is not self._last_screen
        self._last_screen = screen
        fresh = False
        try:
            if screen in _MENU_SCREENS and now - self._last_top_at >= self._top_interval:
                self._read_top(frame, screen)
                self._last_top_at = now
                fresh = True

            if screen in {ScreenState.COLLECTION_MENU, ScreenState.LEAGUE_MENU}:
                detail_due = now - self._last_detail_at.get(screen, float("-inf")) >= self._detail_interval
                if entered or detail_due:
                    # RapidOCR retains per-call overrides in some releases, so
                    # explicitly re-enable detection after fixed-region reads.
                    full_result = self._ocr(
                        frame,
                        use_det=True,
                        use_cls=True,
                        use_rec=True,
                    )
                    if screen is ScreenState.COLLECTION_MENU:
                        self._read_collection(full_result)
                    else:
                        self._read_league(full_result)
                    self._last_detail_at[screen] = now
                    fresh = True
        except Exception as exc:
            logger.warning("Resource OCR failed; retaining last snapshot: {!r}", exc)

        if self._snapshot != snapshot_before:
            self._save_snapshot()

        if not self._snapshot:
            return {"resource_ocr_status": "pending"}
        return {
            "resources": dict(self._snapshot),
            "resource_ocr_status": "fresh" if fresh else "cached",
        }
