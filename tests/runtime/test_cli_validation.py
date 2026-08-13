from pathlib import Path

import cv2
import numpy as np
import pytest

from src.main import build_parser, main


@pytest.mark.parametrize(
    ("args", "option"),
    [
        (["--device", " "], "--device"),
        (["--device", "A", "--frames", "0"], "--frames"),
        (["--device", "A", "--interval", "nan"], "--interval"),
        (["--device", "A", "--interval", "-1"], "--interval"),
    ],
)
def test_parser_rejects_invalid_runtime_arguments(args, option) -> None:
    with pytest.raises(SystemExit) as caught:
        build_parser().parse_args(args)
    assert caught.value.code == 2


def test_main_returns_configuration_error_for_missing_or_empty_replay(tmp_path: Path) -> None:
    assert main(["--replay", str(tmp_path / "missing")]) == 2
    assert main(["--replay", str(tmp_path)]) == 2


def test_main_rejects_request_for_more_frames_than_replay_contains(tmp_path: Path) -> None:
    path = tmp_path / "one.png"
    assert cv2.imwrite(str(path), np.zeros((2, 2, 3), dtype=np.uint8))
    assert main(["--replay", str(tmp_path), "--frames", "2"]) == 2


def test_main_returns_configuration_error_without_traceback_when_runtime_construction_fails(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "one.png"
    assert cv2.imwrite(str(path), np.zeros((2, 2, 3), dtype=np.uint8))

    def missing_templates():
        raise FileNotFoundError("templates missing")

    monkeypatch.setattr("src.main.LegacyVisionAdapter", missing_templates)
    assert main(["--replay", str(tmp_path), "--frames", "1"]) == 2


def test_main_catches_operational_session_construction_failure(monkeypatch) -> None:
    def failing_session(serial):
        raise RuntimeError("adb unavailable")

    monkeypatch.setattr("src.main.DeviceSession", failing_session)
    assert main(["--device", "offline"]) == 1


def test_main_catches_keyboard_interrupt_before_runtime_run(monkeypatch) -> None:
    def interrupted_session(serial):
        raise KeyboardInterrupt()

    monkeypatch.setattr("src.main.DeviceSession", interrupted_session)
    assert main(["--device", "offline"]) == 130


@pytest.mark.parametrize("failure, code", [(KeyboardInterrupt(), 130), (RuntimeError("log failure"), 1)])
def test_main_bounds_setup_logger_failures(monkeypatch, failure, code) -> None:
    monkeypatch.setattr("src.main.setup_logger", lambda level: (_ for _ in ()).throw(failure))
    assert main(["--device", "offline"]) == code


def test_main_catches_keyboard_interrupt_during_replay_validation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("src.main.os.access", lambda path, mode: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert main(["--replay", str(tmp_path)]) == 130


def test_main_reports_replay_source_operational_failure(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "one.png"
    assert cv2.imwrite(str(path), np.zeros((2, 2, 3), dtype=np.uint8))
    monkeypatch.setattr("src.main.ReplayCaptureSource", lambda paths: (_ for _ in ()).throw(RuntimeError("replay boom")))
    assert main(["--replay", str(tmp_path)]) == 1


def test_main_fallback_stderr_survives_failing_logger(monkeypatch, capsys) -> None:
    class BrokenLogger:
        def error(self, *args):
            raise RuntimeError("logger broken")

    monkeypatch.setattr("src.main.setup_logger", lambda level: None)
    monkeypatch.setattr("src.main.logger", BrokenLogger())
    monkeypatch.setattr("src.main.DeviceSession", lambda serial: (_ for _ in ()).throw(RuntimeError("adb down")))
    assert main(["--device", "offline"]) == 1
    assert "runtime failure" in capsys.readouterr().err


def test_main_treats_runtime_value_error_as_operational_failure(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "one.png"
    assert cv2.imwrite(str(path), np.zeros((2, 2, 3), dtype=np.uint8))

    class FailingRuntime:
        def run(self, *, max_frames):
            raise ValueError("perception failed")

    monkeypatch.setattr("src.main.BotRuntime", lambda **kwargs: FailingRuntime())
    assert main(["--replay", str(tmp_path), "--frames", "1"]) == 1
