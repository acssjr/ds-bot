from pathlib import Path

import numpy as np

from src.capture.models import CaptureBackend, CapturedImage, Frame
from src.recording.session_recorder import SessionRecorder


def _frame(frame_id: int, value: int = 20) -> Frame:
    captured = CapturedImage(
        np.full((120, 80, 3), value, dtype=np.uint8),
        float(frame_id),
        CaptureBackend.REPLAY,
    )
    return Frame.from_capture(
        captured,
        frame_id=frame_id,
        device_serial="replay",
        connection_generation=0,
        capture_generation=0,
    )


def test_recorder_saves_useful_frames_and_deduplicates_repetition(tmp_path: Path) -> None:
    moments = iter([0.0, 0.1, 1.0])
    recorder = SessionRecorder(tmp_path, clock=lambda: next(moments))

    first = recorder.record(_frame(1), {"screen": "HOME", "confidence": 0.9})
    repeated = recorder.record(_frame(2), {"screen": "HOME", "confidence": 0.9})
    transition = recorder.record(_frame(3, 200), {"screen": "BATTLE", "confidence": 0.8})
    recorder.close()

    assert first.saved is True
    assert repeated.saved is False
    assert transition.saved is True
    session = Path(transition.session_directory)
    assert len(list((session / "frames").glob("*.jpg"))) == 2
    assert len((session / "observations.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    assert (session / "summary.json").exists()
