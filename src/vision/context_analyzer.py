from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.state.game_state import ScreenState


class ContextAnalyzer:
    """Extract conservative, action-relevant facts after screen classification."""

    def __init__(self, templates_dir: str | Path) -> None:
        indicators = Path(templates_dir) / "indicators"
        self._free_ad_button = self._load(indicators / "free_ad_button.png")
        self._daily_refresh_label = self._load(indicators / "daily_refresh_label.png")
        self._daily_refresh_button = self._load(indicators / "daily_refresh_ad_button.png")

    @staticmethod
    def _load(path: Path) -> np.ndarray | None:
        if not path.is_file():
            return None
        return cv2.imread(str(path), cv2.IMREAD_COLOR)

    @staticmethod
    def _best_score(frame: np.ndarray, template: np.ndarray | None) -> float:
        if template is None or template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
            return 0.0
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        return float(cv2.minMaxLoc(result)[1])

    @staticmethod
    def _count_matches(frame: np.ndarray, template: np.ndarray | None, threshold: float) -> int:
        if template is None or template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
            return 0
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(result >= threshold)
        ranked = sorted(
            ((int(x), int(y), float(result[y, x])) for x, y in zip(xs, ys, strict=True)),
            key=lambda item: item[2],
            reverse=True,
        )
        retained: list[tuple[int, int]] = []
        for x, y, _score in ranked:
            if all(
                abs(x - previous_x) > template.shape[1] * 0.5
                or abs(y - previous_y) > template.shape[0] * 0.5
                for previous_x, previous_y in retained
            ):
                retained.append((x, y))
        return len(retained)

    def analyze(
        self,
        frame: np.ndarray,
        screen: ScreenState,
        sub_element: str | None,
    ) -> dict[str, Any]:
        if screen is ScreenState.SHOP_DAILY_OFFERS:
            return {
                "context": "daily_offers",
                "free_ad_offers_visible": self._count_matches(frame, self._free_ad_button, 0.72),
                "daily_refresh_ad_visible": self._best_score(frame, self._daily_refresh_button) >= 0.80,
                "next_refresh_countdown_visible": self._best_score(frame, self._daily_refresh_label) >= 0.78,
                "next_refresh_text": "OCR_PENDING",
            }
        if screen is ScreenState.SHOP_MENU:
            return {"context": "shop", "paid_and_ad_offers_may_be_visible": True}
        if screen is ScreenState.WATCHING_AD:
            return {
                "context": "rewarded_ad",
                "ad_status": "pending",
                "safe_to_close": False,
                "completion_signal": sub_element or "unconfirmed",
            }
        if screen is ScreenState.AD_REWARD_GRANTED:
            return {
                "context": "rewarded_ad",
                "ad_status": "reward_granted",
                "safe_to_close": True,
                "completion_signal": sub_element or "visual_confirmation",
            }
        if screen is ScreenState.LEAGUE_MENU:
            return {"context": "league", "league": "BRONZE", "trophies_text": "OCR_PENDING"}
        if screen is ScreenState.RANKED_LOCKED:
            return {"context": "ranked", "ranked_unlocked": False}
        if screen is ScreenState.PROFILE_MENU:
            return {"context": "profile", "statistics_visible": True}
        return {}
