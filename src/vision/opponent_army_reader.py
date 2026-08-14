from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np


class OpponentArmyReader:
    """Conservatively identify opponent units visible above the draft cards.

    Templates are small unit sprites extracted from the same installed game
    version as the strategy tables.  A unit is reported only above a calibrated
    high-confidence threshold; the density profile remains useful when a sprite
    is upgraded, recoloured, or occluded and therefore cannot be named safely.
    """

    _TEMPLATES = {
        "Knight": ("knight_enemy_helmet.png", 0.62, (0.18, 0.44)),
        "Cupid": ("cupid_enemy.png", 0.65, (0.24, 0.58)),
        "Goose": ("goose_enemy.png", 0.65, (0.24, 0.58)),
        "TNT": ("tnt_enemy_body.png", 0.70, (0.18, 0.46)),
        "Snail": ("snail_enemy.png", 0.65, (0.24, 0.58)),
        "Assassin": ("assassin_enemy.png", 0.65, (0.24, 0.58)),
        "Kingclops": ("kingclops_enemy.png", 0.65, (0.24, 0.58)),
    }

    def __init__(self, templates_dir: str | Path) -> None:
        directory = Path(templates_dir) / "units"
        self._templates: dict[str, tuple[np.ndarray, float, tuple[float, float]]] = {}
        for unit, (filename, threshold, scales) in self._TEMPLATES.items():
            image = cv2.imread(str(directory / filename), cv2.IMREAD_UNCHANGED)
            if image is not None and image.ndim == 3 and image.shape[2] == 4:
                self._templates[unit] = (image, threshold, scales)
        self._engineer_templates = tuple(
            image
            for filename in (
                "engineer_enemy.png",
                "engineer_enemy_head.png",
                "engineer_enemy_bag2.png",
                "engineer_enemy_bag3.png",
            )
            if (image := cv2.imread(str(directory / filename), cv2.IMREAD_UNCHANGED))
            is not None
            and image.ndim == 3
            and image.shape[2] == 4
        )
        self._seen_units: list[str] = []

    @staticmethod
    def _opponent_region(frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        return frame[
            round(height * 0.15) : round(height * 0.38),
            round(width * 0.12) : round(width * 0.88),
        ]

    @staticmethod
    def _best_score(
        region: np.ndarray,
        template: np.ndarray,
        scale_bounds: tuple[float, float],
    ) -> float:
        best = 0.0
        background = np.median(region.reshape(-1, 3), axis=0).astype(np.uint8)
        for scale in np.arange(scale_bounds[0], scale_bounds[1] + 0.001, 0.03):
            width = max(4, round(template.shape[1] * float(scale)))
            height = max(4, round(template.shape[0] * float(scale)))
            if width >= region.shape[1] or height >= region.shape[0]:
                continue
            colour = cv2.resize(
                template[:, :, :3], (width, height), interpolation=cv2.INTER_AREA
            )
            alpha = cv2.resize(
                template[:, :, 3], (width, height), interpolation=cv2.INTER_AREA
            ).astype(np.float32) / 255.0
            # Compositing transparent pixels over the measured arena colour is
            # over an order of magnitude faster than masked template matching.
            # That keeps all opponent analysis inside the live draft deadline.
            colour = (
                colour * alpha[:, :, None]
                + background * (1.0 - alpha[:, :, None])
            ).astype(np.uint8)
            scores = cv2.matchTemplate(
                region,
                colour,
                cv2.TM_CCOEFF_NORMED,
            )
            if scores.size:
                finite = np.nan_to_num(scores, nan=-1.0, posinf=-1.0, neginf=-1.0)
                best = max(best, float(np.max(finite)))
        return best

    def analyze(self, frame: np.ndarray) -> dict[str, Any]:
        region = self._opponent_region(frame)
        if region.size == 0:
            return {
                "enemy_units": (),
                "enemy_unit_confidence": {},
                "enemy_board_pressure": "unknown",
            }

        scores: dict[str, float] = {}
        detected: list[str] = []
        for unit, (template, threshold, scales) in self._templates.items():
            score = self._best_score(region, template, scales)
            scores[unit] = round(score, 4)
            if score >= threshold:
                detected.append(unit)

        if self._engineer_templates:
            engineer_scores = sorted(
                (
                    self._best_score(region, template, (0.14, 0.36))
                    for template in self._engineer_templates
                ),
                reverse=True,
            )
            # Requiring two independently matching sprite components avoids
            # mistaking the similarly coloured Knight armour for Engineer.
            engineer_score = engineer_scores[1] if len(engineer_scores) >= 2 else 0.0
            scores["Engineer"] = round(engineer_score, 4)
            if engineer_score >= 0.45:
                detected.append("Engineer")

        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        green = cv2.inRange(hsv, np.array([38, 100, 90]), np.array([88, 255, 255]))
        green_ratio = float(np.mean(green > 0))
        if green_ratio >= 0.0025:
            detected.append("Splime")
            scores["Splime"] = round(min(1.0, 0.75 + green_ratio * 40.0), 4)

        coloured_ratio = float(np.mean((saturation > 70) & (value > 75)))
        if coloured_ratio >= 0.13:
            pressure = "high"
        elif coloured_ratio >= 0.045:
            pressure = "moderate"
        else:
            pressure = "low"

        for unit in detected:
            if unit not in self._seen_units:
                self._seen_units.append(unit)

        return {
            "enemy_units": tuple(self._seen_units),
            "enemy_unit_confidence": scores,
            "enemy_board_pressure": pressure,
            "enemy_board_coloured_ratio": round(coloured_ratio, 4),
        }
