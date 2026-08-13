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
            return ScreenState.UNKNOWN, 0.0, None
        if accepted:
            return best_template.screen, best_score, best_template.template_id
        return (
            ScreenState.UNKNOWN,
            best_score,
            f"candidate:{best_template.screen.value}/{best_template.template_id}",
        )
