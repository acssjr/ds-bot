import math
from typing import Tuple

import numpy as np


class CoordinateConverter:
    """Compatibility adapter for normalized framebuffer coordinates."""

    @staticmethod
    def normalize(
        pixel_x: int,
        pixel_y: int,
        screen_width: int,
        screen_height: int,
    ) -> Tuple[float, float]:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")
        if not (0 <= pixel_x < screen_width and 0 <= pixel_y < screen_height):
            raise ValueError("pixel coordinates must be inside the screen")
        nx = 0.0 if screen_width == 1 else pixel_x / (screen_width - 1)
        ny = 0.0 if screen_height == 1 else pixel_y / (screen_height - 1)
        return nx, ny

    @staticmethod
    def denormalize(
        norm_x: float,
        norm_y: float,
        screen_width: int,
        screen_height: int,
    ) -> Tuple[int, int]:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")
        if not (0.0 <= norm_x <= 1.0 and 0.0 <= norm_y <= 1.0):
            raise ValueError("normalized coordinates must be between 0 and 1")
        x = round(norm_x * max(0, screen_width - 1))
        y = round(norm_y * max(0, screen_height - 1))
        return x, y

    @staticmethod
    def crop_roi(image, norm_box: Tuple[float, float, float, float]):
        if not isinstance(image, np.ndarray) or image.ndim < 2:
            raise ValueError("image must be a non-empty array with at least two dimensions")
        height, width = image.shape[:2]
        if height <= 0 or width <= 0:
            raise ValueError("image must be a non-empty array with at least two dimensions")
        left, top, right, bottom = norm_box
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            raise ValueError("ROI must be ordered and inside the normalized screen")
        x1 = max(0, min(width, math.floor(left * width)))
        y1 = max(0, min(height, math.floor(top * height)))
        x2 = max(0, min(width, math.ceil(right * width)))
        y2 = max(0, min(height, math.ceil(bottom * height)))
        return image[y1:y2, x1:x2]
