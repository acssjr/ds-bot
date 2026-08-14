from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from src.state.game_state import ScreenState
from src.vision.classifiers.screen_classifier import ScreenClassifier
from src.vision.draft_reader import DraftCardReader
from src.vision.opponent_army_reader import OpponentArmyReader


class ContextAnalyzer:
    """Extract conservative, action-relevant facts after screen classification."""

    def __init__(
        self,
        templates_dir: str | Path,
        *,
        draft_reader: DraftCardReader | None = None,
        opponent_reader: OpponentArmyReader | None = None,
    ) -> None:
        templates = Path(templates_dir)
        indicators = templates / "indicators"
        self._free_ad_button = self._load(indicators / "free_ad_button.png")
        self._daily_refresh_label = self._load(indicators / "daily_refresh_label.png")
        self._daily_refresh_button = self._load(indicators / "daily_refresh_ad_button.png")
        self._recovery_banner = self._load(templates / "automation" / "recovery_banner_verified.png")
        self._ad_endcard_close = self._load(templates / "ads" / "endcard_close_verified.png")
        self._ad_reward_granted = self._load(templates / "ads" / "reward_granted_verified.png")
        self._draft_reader = draft_reader or DraftCardReader()
        self._opponent_reader = opponent_reader or OpponentArmyReader(templates)

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
    def _best_match(
        frame: np.ndarray,
        template: np.ndarray | None,
    ) -> tuple[float, tuple[int, int]] | None:
        if template is None or template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
            return None
        result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
        _minimum, score, _minimum_location, location = cv2.minMaxLoc(result)
        return float(score), (int(location[0]), int(location[1]))

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
        if screen is ScreenState.DRAFT_SCREEN:
            slots = self._draft_available_slots(frame)
            cards = self._draft_reader.read(frame, slots)
            result = {
                "context": "draft",
                "draft_available_slots": slots,
                "draft_variant": "recovery_bonus" if self._has_recovery_banner(frame) else "normal_pick",
                "draft_choices": tuple(card.payload() for card in cards),
            }
            result.update(self._opponent_reader.analyze(frame))
            return result
        if screen is ScreenState.VICTORY_SUMMARY:
            return self._victory_context(frame, sub_element)
        if screen is ScreenState.DEFEAT_SUMMARY:
            return {
                "context": "defeat",
                "match_outcome": "defeat",
                "defeat_phase": "mastery_distribution",
                "tap_to_skip_visible": True,
            }
        if screen is ScreenState.DOUBLE_BITS:
            return {
                "context": "double_bits",
                "double_bits_ad_available": True,
                "continue_visible": True,
            }
        if screen is ScreenState.MASTERY_BOOST:
            result = {
                "context": "mastery_boost",
                "boost_available_slots": self._boost_available_slots(frame),
                "continue_visible": True,
                "spending_currency": "mastery_currency",
            }
            if sub_element == "ocr:defeat_mastery_boost":
                result["match_outcome"] = "defeat"
            return result
        if screen is ScreenState.BIT_PACK_OPENING:
            return {"context": "bit_pack", "tap_to_skip_visible": True}
        if screen is ScreenState.NEW_UNIT_UNLOCKED:
            return {"context": "new_unit", "continue_visible": True}
        if screen is ScreenState.POST_BATTLE_OFFER:
            close = self._post_battle_offer_close(frame)
            payload: dict[str, Any] = {
                "context": "post_battle_offer",
                "purchase_allowed": False,
                "offer_close_visible": close is not None,
            }
            if close is not None:
                height, width = frame.shape[:2]
                payload["offer_close_point"] = (close[0] / width, close[1] / height)
            return payload
        if screen is ScreenState.SHOP_DAILY_OFFERS:
            free_ad_offers = self._count_matches(frame, self._free_ad_button, 0.72)
            refresh_ad_visible = self._best_score(frame, self._daily_refresh_button) >= 0.80
            countdown_visible = self._best_score(frame, self._daily_refresh_label) >= 0.78
            return {
                "context": "daily_offers",
                "free_ad_offers_visible": free_ad_offers,
                "ad_reward_available_now": free_ad_offers > 0,
                "daily_refresh_ad_visible": refresh_ad_visible,
                "daily_refresh_available_now": refresh_ad_visible,
                "next_refresh_countdown_visible": countdown_visible,
                "next_reward_status": (
                    "AVAILABLE_NOW"
                    if free_ad_offers > 0
                    else "COOLDOWN_VISIBLE" if countdown_visible else "NOT_VISIBLE"
                ),
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
            payload: dict[str, Any] = {
                "context": "rewarded_ad",
                "ad_status": "reward_granted",
                "safe_to_close": True,
                "completion_signal": sub_element or "visual_confirmation",
            }
            close = self._ad_close_point(frame, sub_element)
            payload["ad_close_visible"] = close is not None
            if close is not None:
                height, width = frame.shape[:2]
                payload["ad_close_point"] = (close[0] / width, close[1] / height)
            return payload
        if screen is ScreenState.LEAGUE_MENU:
            return {"context": "league", "league": "BRONZE", "trophies_text": "OCR_PENDING"}
        if screen is ScreenState.RANKED_LOCKED:
            return {"context": "ranked", "ranked_unlocked": False}
        if screen is ScreenState.PROFILE_MENU:
            return {"context": "profile", "statistics_visible": True}
        return {}

    @staticmethod
    def _draft_available_slots(frame: np.ndarray) -> tuple[int, ...]:
        height, width = frame.shape[:2]
        slots: list[int] = []
        for index, (left, right) in enumerate(((0.02, 0.33), (0.34, 0.66), (0.67, 0.98))):
            card = frame[
                round(height * 0.42) : round(height * 0.70),
                round(width * left) : round(width * right),
            ]
            hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
            gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
            saturated_ratio = float(np.mean(hsv[:, :, 1] > 70))
            edge_ratio = float(np.mean(cv2.Canny(gray, 80, 160) > 0))
            if saturated_ratio >= 0.45 and edge_ratio >= 0.065:
                slots.append(index)
        return tuple(slots)

    def _has_recovery_banner(self, frame: np.ndarray) -> bool:
        return self._best_score(frame, self._recovery_banner) >= 0.80

    @staticmethod
    def _victory_context(frame: np.ndarray, sub_element: str | None) -> dict[str, Any]:
        height, width = frame.shape[:2]
        if sub_element == "ocr:victory_reward_available":
            return {
                "context": "victory",
                "victory_phase": "package_ready",
                "continue_visible": True,
                "reward_ad_available": True,
            }
        if sub_element == "ocr:victory_reward_cooldown":
            return {
                "context": "victory",
                "victory_phase": "package_ready",
                "continue_visible": True,
                "reward_ad_available": False,
                "reward_ad_cooldown": True,
            }
        if sub_element == "victory_package":
            button = frame[
                round(height * 0.85) : round(height * 0.97),
                round(width * 0.50) : round(width * 0.95),
            ]
            hsv = cv2.cvtColor(button, cv2.COLOR_BGR2HSV)
            tan = cv2.inRange(hsv, np.array([5, 20, 80]), np.array([40, 220, 255]))
            ready = bool(np.mean(tan > 0) >= 0.18)
            return {
                "context": "victory",
                "victory_phase": "package_ready" if ready else "package_animating",
                "continue_visible": ready,
                "reward_ad_available": False,
            }

        cards = frame[
            round(height * 0.38) : round(height * 0.64),
            round(width * 0.02) : round(width * 0.98),
        ]
        hsv = cv2.cvtColor(cards, cv2.COLOR_BGR2HSV)
        tan = cv2.inRange(hsv, np.array([5, 25, 125]), np.array([40, 235, 255]))
        mastery = bool(np.mean(tan > 0) >= 0.12)
        return {
            "context": "victory",
            "victory_phase": "mastery_distribution" if mastery else "splash",
            "continue_visible": False,
        }

    @staticmethod
    def _post_battle_offer_close(frame: np.ndarray) -> tuple[int, int] | None:
        return ScreenClassifier._post_battle_offer_close(frame)

    @staticmethod
    def _boost_available_slots(frame: np.ndarray) -> tuple[int, ...]:
        height, width = frame.shape[:2]
        slots: list[int] = []
        for index in range(4):
            left = round(width * (0.01 + index * 0.245))
            right = round(width * (0.25 + index * 0.245))
            button = frame[round(height * 0.56) : round(height * 0.68), left:right]
            if button.size == 0:
                continue
            hsv = cv2.cvtColor(button, cv2.COLOR_BGR2HSV)
            green = cv2.inRange(hsv, np.array([35, 60, 70]), np.array([95, 255, 255]))
            if float(np.mean(green > 0)) >= 0.08:
                slots.append(index)
        return tuple(slots)

    def _ad_close_point(
        self,
        frame: np.ndarray,
        sub_element: str | None,
    ) -> tuple[int, int] | None:
        template = (
            self._ad_reward_granted
            if sub_element == "ad_reward_granted"
            else self._ad_endcard_close
        )
        matched = self._best_match(frame, template)
        threshold = 0.78 if sub_element == "ad_reward_granted" else 0.82
        if matched is None or matched[0] < threshold or template is None:
            return None
        x, y = matched[1]
        if sub_element == "ad_reward_granted":
            return x + round(template.shape[1] * 0.16), y + template.shape[0] // 2
        return x + template.shape[1] // 2, y + template.shape[0] // 2
