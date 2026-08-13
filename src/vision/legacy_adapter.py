from __future__ import annotations

from pathlib import Path
from typing import Any

from src.state.game_state import ScreenState
from src.core.cancellation import CancellationToken
from src.vision.pipeline import VisionPipeline


class LegacyVisionAdapter:
    def __init__(self, templates_dir: str = "assets/templates"):
        root = Path(__file__).resolve().parents[2]
        configured = Path(templates_dir)
        resolved = configured if configured.is_absolute() else root / configured
        resolved = resolved.resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"templates directory does not exist: {resolved}")
        self._pipeline = VisionPipeline(templates_dir=str(resolved))

    def analyze(self, image, *, cancellation: CancellationToken | None = None) -> dict[str, Any]:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        if cancellation is None:
            result = dict(self._pipeline.analyze(image))
        else:
            result = dict(self._pipeline.analyze(image, cancellation=cancellation))
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        screen = result.get("screen", ScreenState.UNKNOWN)
        try:
            result["screen"] = screen.value if isinstance(screen, ScreenState) else ScreenState(screen).value
        except (TypeError, ValueError):
            result["screen"] = ScreenState.UNKNOWN.value
        result.pop("available_choices", None)
        result.pop("frame_shape", None)
        return result


LegacyVisionPerception = LegacyVisionAdapter
