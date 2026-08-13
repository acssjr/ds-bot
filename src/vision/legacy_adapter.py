from __future__ import annotations

from typing import Any

from src.state.game_state import ScreenState
from src.vision.pipeline import VisionPipeline


class LegacyVisionAdapter:
    def __init__(self, templates_dir: str = "assets/templates"):
        self._pipeline = VisionPipeline(templates_dir=templates_dir)

    def analyze(self, image) -> dict[str, Any]:
        result = dict(self._pipeline.analyze(image))
        screen = result.get("screen", ScreenState.UNKNOWN)
        result["screen"] = screen.value if isinstance(screen, ScreenState) else str(screen)
        result.pop("available_choices", None)
        result.pop("frame_shape", None)
        return result
