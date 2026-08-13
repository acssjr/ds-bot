from __future__ import annotations

import random

from src.geometry.models import DisplayProfile, NormalizedPoint, PixelPoint, RectXYXY


class CoordinateMapper:
    def __init__(self, profile: DisplayProfile):
        self.profile = profile

    def normalized_to_framebuffer(self, point: NormalizedPoint) -> PixelPoint:
        rect = self.profile.content_rect
        x = rect.left + round(point.x * max(0, rect.width - 1))
        y = rect.top + round(point.y * max(0, rect.height - 1))
        return PixelPoint(
            min(max(x, rect.left), rect.right - 1),
            min(max(y, rect.top), rect.bottom - 1),
        )

    def sample_target(
        self,
        target: RectXYXY,
        *,
        inset_px: int,
        rng: random.Random,
    ) -> PixelPoint:
        safe = target.inset(inset_px) if inset_px else target
        point = PixelPoint(
            rng.randint(safe.left, safe.right - 1),
            rng.randint(safe.top, safe.bottom - 1),
        )
        if not target.contains(point):
            raise AssertionError("sampled point escaped target")
        return point
