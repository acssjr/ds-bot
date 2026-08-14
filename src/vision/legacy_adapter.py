from __future__ import annotations

from importlib import resources
from os import PathLike
from pathlib import Path
from typing import Any

from src.state.game_state import ScreenState
from src.core.cancellation import CancellationToken
from src.vision.pipeline import VisionPipeline
from src.vision.resource_reader import ResourceReader


class LegacyVisionAdapter:
    def __init__(
        self,
        templates_dir: str | PathLike[str] | None = None,
        *,
        resource_reader: ResourceReader | None = None,
    ) -> None:
        if templates_dir is None:
            self._pipeline = self._pipeline_from_packaged_templates(resource_reader)
            return

        resolved = Path(templates_dir).expanduser().resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"templates directory does not exist: {resolved}")
        self._pipeline = VisionPipeline(
            templates_dir=str(resolved),
            resource_reader=resource_reader
            or ResourceReader(state_path="datasets/account_state.json"),
        )

    @staticmethod
    def _pipeline_from_packaged_templates(
        resource_reader: ResourceReader | None = None,
    ) -> VisionPipeline:
        try:
            templates = resources.files("assets").joinpath("templates")
        except (ModuleNotFoundError, TypeError) as exc:
            raise FileNotFoundError(
                "packaged templates resource is unavailable"
            ) from exc
        if not templates.is_dir():
            raise FileNotFoundError("packaged templates directory is unavailable")

        # ScreenClassifier loads every image eagerly, so extracted zip resources
        # can be released as soon as VisionPipeline construction completes.
        with resources.as_file(templates) as materialized:
            if not materialized.is_dir():
                raise FileNotFoundError(
                    "packaged templates directory could not be materialized"
                )
            return VisionPipeline(
                templates_dir=str(materialized),
                resource_reader=resource_reader
                or ResourceReader(state_path="datasets/account_state.json"),
            )

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
