from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from loguru import logger

from src.core.cancellation import CancellationToken
from src.state.game_state import ScreenState


@dataclass(frozen=True, slots=True)
class LoadedTemplate:
    template_id: str
    screen: ScreenState
    image: np.ndarray
    threshold: float
    roi: tuple[float, float, float, float]
    scales: tuple[float, ...]


class ScreenClassifier:
    """Recognize verified screen anchors inside constrained screen regions."""

    def __init__(self, templates_dir: str = "assets/templates"):
        self.templates_dir = str(Path(templates_dir).resolve())
        root = Path(self.templates_dir)
        if not root.is_dir():
            raise FileNotFoundError(
                f"templates directory does not exist: {self.templates_dir}"
            )
        self.templates = self._load_manifest(root)

    def _load_manifest(self, root: Path) -> tuple[LoadedTemplate, ...]:
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            # Explicit custom directories remain compatible with the old
            # loader. Packaged production assets always contain a manifest.
            return self._load_legacy_templates(root)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        loaded: list[LoadedTemplate] = []
        for entry in manifest.get("templates", []):
            image_path = root / entry["path"]
            image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(
                    f"verified template image cannot be read: {image_path}"
                )
            roi = tuple(float(value) for value in entry["roi"])
            if len(roi) != 4 or not (
                0.0 <= roi[0] < roi[2] <= 1.0
                and 0.0 <= roi[1] < roi[3] <= 1.0
            ):
                raise ValueError(f"invalid ROI for template {entry['id']!r}")
            scales = tuple(float(value) for value in entry.get("scales", [1.0]))
            loaded.append(
                LoadedTemplate(
                    template_id=str(entry["id"]),
                    screen=ScreenState(entry["screen"]),
                    image=image,
                    threshold=float(entry["threshold"]),
                    roi=roi,
                    scales=scales,
                )
            )
            logger.debug(
                "Verified template loaded [{}]: {}",
                entry["screen"],
                entry["id"],
            )
        if not loaded:
            raise ValueError("verified template manifest contains no templates")
        return tuple(loaded)

    @staticmethod
    def _load_legacy_templates(root: Path) -> tuple[LoadedTemplate, ...]:
        folder_to_state = {
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
            "shop": ScreenState.SHOP_MENU,
            "shop_daily_offers": ScreenState.SHOP_DAILY_OFFERS,
            "ads": ScreenState.WATCHING_AD,
            "ad_reward_granted": ScreenState.AD_REWARD_GRANTED,
            "league": ScreenState.LEAGUE_MENU,
            "ranked": ScreenState.RANKED_LOCKED,
            "profile": ScreenState.PROFILE_MENU,
        }
        loaded: list[LoadedTemplate] = []
        for folder, screen in folder_to_state.items():
            for image_path in sorted((root / folder).glob("*")):
                if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                    continue
                image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                loaded.append(
                    LoadedTemplate(
                        template_id=image_path.stem,
                        screen=screen,
                        image=image,
                        threshold=0.70,
                        roi=(0.0, 0.0, 1.0, 1.0),
                        scales=(1.0,),
                    )
                )
        return tuple(loaded)

    def classify(
        self,
        frame: np.ndarray,
        *,
        cancellation: CancellationToken | None = None,
    ) -> tuple[ScreenState, float, Optional[str]]:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        if frame is None or frame.size == 0:
            return ScreenState.UNKNOWN, 0.0, None
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be an HxWx3 BGR image")
        if frame.max() <= 8 or (frame.mean() <= 2.0 and frame.std() <= 2.0):
            return ScreenState.UNKNOWN, 0.0, "blank_frame"
        offer_close = self._post_battle_offer_close(frame)
        if offer_close is not None:
            return ScreenState.POST_BATTLE_OFFER, 0.95, "post_battle_offer_close"
        if self._has_ad_progress_bar(frame):
            return ScreenState.WATCHING_AD, 0.90, "ad_progress_pending"

        best_score = 0.0
        best_template: LoadedTemplate | None = None
        accepted = False

        height, width = frame.shape[:2]
        for template in self.templates:
            if cancellation is not None:
                cancellation.raise_if_cancelled()
            left = round(template.roi[0] * width)
            top = round(template.roi[1] * height)
            right = round(template.roi[2] * width)
            bottom = round(template.roi[3] * height)
            region = frame[top:bottom, left:right]

            for scale in template.scales:
                resized_width = max(1, round(template.image.shape[1] * scale))
                resized_height = max(1, round(template.image.shape[0] * scale))
                if resized_width > region.shape[1] or resized_height > region.shape[0]:
                    continue
                interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
                candidate = cv2.resize(
                    template.image,
                    (resized_width, resized_height),
                    interpolation=interpolation,
                )
                result = cv2.matchTemplate(
                    region,
                    candidate,
                    cv2.TM_CCOEFF_NORMED,
                )
                _, score, _, _ = cv2.minMaxLoc(result)
                score = float(score)
                if score > best_score:
                    best_score = score
                    best_template = template
                    accepted = score >= template.threshold

        if best_template is None:
            if self._is_round_result(frame):
                return ScreenState.ROUND_RESULT, 0.85, "split_score_panel"
            return ScreenState.UNKNOWN, 0.0, None
        if accepted:
            screen = best_template.screen
            sub_element = best_template.template_id
            if screen is ScreenState.COMBAT and self._has_draft_choices(frame):
                screen = ScreenState.DRAFT_SCREEN
                sub_element = f"{best_template.template_id}:choice_cards"
            return screen, best_score, sub_element
        if self._is_round_result(frame):
            return ScreenState.ROUND_RESULT, 0.85, "split_score_panel"
        return (
            ScreenState.UNKNOWN,
            best_score,
            f"candidate:{best_template.screen.value}/{best_template.template_id}",
        )

    @staticmethod
    def _has_draft_choices(frame: np.ndarray) -> bool:
        """Detect the large tan choice cards while the stable battle HUD is present."""
        height = frame.shape[0]
        region = frame[round(height * 0.30) : round(height * 0.82), :]
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        tan_pixels = cv2.inRange(
            hsv,
            np.array([5, 25, 145], dtype=np.uint8),
            np.array([40, 230, 255], dtype=np.uint8),
        )
        return bool(np.mean(tan_pixels > 0) >= 0.10)

    @staticmethod
    def _is_round_result(frame: np.ndarray) -> bool:
        """Recognize the red/blue between-round score panel without player text."""
        height, width = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        center = hsv[round(height * 0.18) : round(height * 0.82), round(width * 0.08) : round(width * 0.92)]
        split = center.shape[0] // 2
        top = center[:split]
        bottom = center[split:]
        red = cv2.inRange(top, np.array([0, 70, 120]), np.array([12, 255, 255]))
        blue = cv2.inRange(bottom, np.array([90, 45, 90]), np.array([135, 255, 255]))
        return bool(np.mean(red > 0) >= 0.35 and np.mean(blue > 0) >= 0.35)

    @staticmethod
    def _has_ad_progress_bar(frame: np.ndarray) -> bool:
        """Detect rewarded-ad SDKs that expose a thin yellow progress bar."""
        top = cv2.cvtColor(frame[:24], cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(
            top,
            np.array([18, 70, 120], dtype=np.uint8),
            np.array([42, 255, 255], dtype=np.uint8),
        )
        bar_ratio = float(np.mean(yellow[:7] > 0))
        content_ratio = float(np.mean(yellow[9:24] > 0))
        return bool(bar_ratio >= 0.005 and content_ratio < 0.15 and bar_ratio > content_ratio + 0.005)

    @staticmethod
    def _post_battle_offer_close(frame: np.ndarray) -> tuple[int, int] | None:
        """Locate the pink X on the in-game paid offer, never an ad close X."""
        height, width = frame.shape[:2]
        left, top = round(width * 0.78), round(height * 0.28)
        right, bottom = round(width * 0.93), round(height * 0.40)
        region = frame[top:bottom, left:right]
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        red = cv2.bitwise_or(
            cv2.inRange(hsv, np.array([0, 70, 100]), np.array([12, 255, 255])),
            cv2.inRange(hsv, np.array([165, 70, 100]), np.array([179, 255, 255])),
        )
        contours, _ = cv2.findContours(red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contour = max(contours, key=cv2.contourArea)
        x, y, box_width, box_height = cv2.boundingRect(contour)
        area_ratio = cv2.contourArea(contour) / max(1.0, float(region.size // 3))
        square_ratio = box_width / max(1, box_height)
        isolated = (
            x > 0
            and y > 0
            and x + box_width < region.shape[1]
            and y + box_height < region.shape[0]
        )
        normalized_width = box_width / width
        normalized_height = box_height / height
        if (
            area_ratio < 0.10
            or not 0.75 <= square_ratio <= 1.25
            or not isolated
            or not 0.055 <= normalized_width <= 0.11
            or not 0.030 <= normalized_height <= 0.070
        ):
            return None

        button = hsv[y : y + box_height, x : x + box_width]
        margin_y = max(1, box_height // 5)
        margin_x = max(1, box_width // 5)
        button_center = button[
            margin_y : box_height - margin_y,
            margin_x : box_width - margin_x,
        ]
        white_x_ratio = float(
            np.mean(
                (button_center[:, :, 1] < 70)
                & (button_center[:, :, 2] > 190)
            )
        )
        if white_x_ratio < 0.30:
            return None

        panel = cv2.cvtColor(
            frame[round(height * 0.30) : round(height * 0.72), round(width * 0.06) : round(width * 0.94)],
            cv2.COLOR_BGR2HSV,
        )
        bright_panel_ratio = float(np.mean((panel[:, :, 1] < 155) & (panel[:, :, 2] > 165)))
        if bright_panel_ratio < 0.30:
            return None
        return left + x + box_width // 2, top + y + box_height // 2
