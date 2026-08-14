from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.vision.opponent_army_reader import OpponentArmyReader


TEMPLATES = Path(__file__).resolve().parents[2] / "assets" / "templates"


def _place_rgba(frame: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    height, width = rgba.shape[:2]
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    target = frame[y : y + height, x : x + width]
    target[:] = (rgba[:, :, :3] * alpha + target * (1.0 - alpha)).astype(np.uint8)


def test_reader_detects_enemy_sprite_and_carries_confirmed_pick() -> None:
    reader = OpponentArmyReader(TEMPLATES)
    frame = np.full((1280, 720, 3), (180, 175, 185), dtype=np.uint8)
    source = cv2.imread(
        str(TEMPLATES / "units" / "knight_enemy_helmet.png"),
        cv2.IMREAD_UNCHANGED,
    )
    sprite = cv2.resize(source, None, fx=0.30, fy=0.30, interpolation=cv2.INTER_AREA)
    _place_rgba(frame, sprite, 340, 250)

    detected = reader.analyze(frame)
    occluded = reader.analyze(np.full_like(frame, (180, 175, 185)))

    assert "Knight" in detected["enemy_units"]
    assert "Knight" in occluded["enemy_units"]
