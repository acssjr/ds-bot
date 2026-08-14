from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np

from src.capture.models import Frame


@dataclass(frozen=True, slots=True)
class RecordingResult:
    saved: bool
    saved_count: int
    reason: str
    relative_path: str | None
    session_directory: str


class SessionRecorder:
    """Save a compact, automatically selected visual dataset from live play."""

    def __init__(
        self,
        root: Path | str = "datasets/sessions",
        *,
        clock=time.monotonic,
        min_interval_seconds: float = 0.75,
        unknown_interval_seconds: float = 1.5,
        heartbeat_seconds: float = 6.0,
        visual_change_threshold: float = 0.045,
    ) -> None:
        self._root = Path(root)
        self._clock = clock
        self._min_interval = min_interval_seconds
        self._unknown_interval = unknown_interval_seconds
        self._heartbeat = heartbeat_seconds
        self._change_threshold = visual_change_threshold
        self._session_dir: Path | None = None
        self._frames_dir: Path | None = None
        self._metadata_path: Path | None = None
        self._last_signature: np.ndarray | None = None
        self._last_screen: str | None = None
        self._last_saved_at: float | None = None
        self._last_unknown_at: float | None = None
        self._saved_count = 0

    @property
    def saved_count(self) -> int:
        return self._saved_count

    @property
    def session_directory(self) -> str:
        return str(self._session_dir) if self._session_dir is not None else str(self._root)

    def _ensure_session(self) -> None:
        if self._session_dir is not None:
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        session_dir = self._root / stamp
        frames_dir = session_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=False)
        self._session_dir = session_dir
        self._frames_dir = frames_dir
        self._metadata_path = session_dir / "observations.jsonl"
        manifest = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "automatic selective observe-only dataset",
            "image_format": "jpeg",
        }
        (session_dir / "session.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _signature(image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (64, 96), interpolation=cv2.INTER_AREA)

    def record(self, frame: Frame, observation: Mapping[str, Any]) -> RecordingResult:
        now = self._clock()
        screen = str(observation.get("screen") or "UNKNOWN").upper()
        try:
            confidence = float(observation.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        signature = self._signature(frame.image)
        difference = (
            1.0
            if self._last_signature is None
            else float(np.mean(cv2.absdiff(signature, self._last_signature))) / 255.0
        )
        elapsed = float("inf") if self._last_saved_at is None else now - self._last_saved_at
        unknown_elapsed = float("inf") if self._last_unknown_at is None else now - self._last_unknown_at

        reason = ""
        if self._saved_count == 0:
            reason = "session_start"
        elif self._last_screen is not None and screen != self._last_screen:
            reason = "screen_transition"
        elif screen == "UNKNOWN" and unknown_elapsed >= self._unknown_interval:
            reason = "unknown_sample"
        elif difference >= self._change_threshold and elapsed >= self._min_interval:
            reason = "visual_change"
        elif elapsed >= self._heartbeat:
            reason = "heartbeat"

        self._last_signature = signature
        self._last_screen = screen
        if not reason:
            return RecordingResult(False, self._saved_count, "deduplicated", None, self.session_directory)

        self._ensure_session()
        assert self._frames_dir is not None and self._metadata_path is not None and self._session_dir is not None
        safe_screen = "".join(char if char.isalnum() else "_" for char in screen)[:32]
        filename = f"frame_{frame.id:07d}_{safe_screen}_{reason}.jpg"
        target = self._frames_dir / filename
        if not cv2.imwrite(str(target), frame.image, [cv2.IMWRITE_JPEG_QUALITY, 92]):
            raise OSError(f"failed to write dataset image: {target}")
        self._saved_count += 1
        self._last_saved_at = now
        if screen == "UNKNOWN":
            self._last_unknown_at = now
        metadata = {
            "frame_id": frame.id,
            "captured_at_monotonic": frame.captured_at_monotonic,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "screen": screen,
            "confidence": max(0.0, min(1.0, confidence)),
            "sub_element": observation.get("sub_element"),
            "reason": reason,
            "visual_difference": round(difference, 6),
            "width": frame.size.width,
            "height": frame.size.height,
            "file": f"frames/{filename}",
        }
        with self._metadata_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        return RecordingResult(True, self._saved_count, reason, metadata["file"], str(self._session_dir))

    def record_action(self, payload: Mapping[str, Any]) -> None:
        if not isinstance(payload, Mapping):
            raise TypeError("action payload must be a mapping")
        if not all(isinstance(key, str) for key in payload):
            raise TypeError("action payload keys must be strings")
        self._ensure_session()
        assert self._session_dir is not None
        entry = {
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            **dict(payload),
        }
        with (self._session_dir / "actions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def close(self) -> None:
        if self._session_dir is None:
            return
        summary = {
            "closed_at_utc": datetime.now(timezone.utc).isoformat(),
            "saved_frames": self._saved_count,
        }
        (self._session_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
