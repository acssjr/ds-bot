from __future__ import annotations

import argparse
import math
import sys

from loguru import logger

from src.automation.battle_runner import BattleRunner, BattleSettings
from src.automation.game_launcher import GameLauncher
from src.automation.live_input import LiveAdbInput
from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.core.cancellation import CancellationToken
from src.core.events import LoggingEventSink
from src.device.session import DeviceSession
from src.recording.session_recorder import SessionRecorder
from src.recovery.app_supervisor import RewardedAdAppSupervisor
from src.utils.logging_config import setup_logger
from src.vision.legacy_adapter import LegacyVisionAdapter


def _serial(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("--device must not be empty")
    return normalized


def _positive_minutes(value: str) -> float:
    try:
        minutes = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-minutes must be a positive finite number") from exc
    if not math.isfinite(minutes) or minutes <= 0:
        raise argparse.ArgumentTypeError("--max-minutes must be a positive finite number")
    return minutes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Draft Showdown explicit one-battle live executor"
    )
    parser.add_argument("--device", required=True, type=_serial, help="exact ADB serial")
    parser.add_argument(
        "--confirm-live-input",
        required=True,
        action="store_true",
        help="required acknowledgement that this command sends real taps",
    )
    parser.add_argument(
        "--max-minutes",
        type=_positive_minutes,
        default=None,
        help="optional wall-clock limit; matchmaking otherwise has no artificial timeout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logger("INFO")
    try:
        session = DeviceSession(args.device, timeout_seconds=5.0)
        capture = CaptureManager(
            ADBCaptureSource(session),
            device_serial=session.serial,
            connection_generation=lambda: session.connection_generation,
        )
        events = LoggingEventSink(logger)
        cancellation = CancellationToken()
        GameLauncher(session, events=events).ensure_foreground(cancellation)
        recorder = SessionRecorder()
        runner = BattleRunner(
            capture=capture,
            perception=LegacyVisionAdapter(),
            input_backend=LiveAdbInput(session=session, events=events),
            cancellation=cancellation,
            settings=BattleSettings(
                max_runtime_seconds=(args.max_minutes * 60.0 if args.max_minutes is not None else None)
            ),
            recorder=recorder,
            events=events,
            recovery=RewardedAdAppSupervisor(session),
        )
        logger.warning(
            "LIVE INPUT ENABLED for one battle on {}; rewarded ads and bounded mastery boosts enabled; real-money, gem and coin purchases disabled",
            session.serial,
        )
        result = runner.run()
        if not result.completed:
            logger.warning(
                "battle executor stopped before HOME: phase={}, frames={}, actions={}",
                result.final_phase.value,
                result.frames,
                result.actions,
            )
            return 130
        logger.info(
            "battle complete at HOME: frames={}, actions={}",
            result.frames,
            result.actions,
        )
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logger.error("one-battle executor failed safely: {!r}", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
