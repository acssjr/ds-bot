from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

from loguru import logger

from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.capture.replay import ReplayCaptureSource
from src.core.cancellation import CancellationToken
from src.core.events import LoggingEventSink
from src.core.lifecycle import Lifecycle
from src.device.session import DeviceSession
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.utils.logging_config import setup_logger
from src.vision.legacy_adapter import LegacyVisionAdapter


class _ConfigurationError(RuntimeError):
    pass


def _device_serial(value: str) -> str:
    serial = value.strip()
    if not serial:
        raise argparse.ArgumentTypeError("--device must not be empty")
    return serial


def _positive_frames(value: str) -> int:
    try:
        frames = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--frames must be a positive integer") from exc
    if frames <= 0:
        raise argparse.ArgumentTypeError("--frames must be a positive integer")
    return frames


def _poll_interval(value: str) -> float:
    try:
        interval = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--interval must be a finite non-negative number") from exc
    if not math.isfinite(interval) or interval < 0:
        raise argparse.ArgumentTypeError("--interval must be a finite non-negative number")
    return interval


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft Showdown observe-only runtime")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", type=_device_serial, help="explicit ADB serial, for example 127.0.0.1:21503")
    source.add_argument("--replay", type=Path, help="directory containing replay PNG/JPG files")
    parser.add_argument("--frames", type=_positive_frames, default=None, help="stop after this many frames")
    parser.add_argument("--interval", type=_poll_interval, default=0.25, help="seconds between frames")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _main(args)
    except KeyboardInterrupt:
        return 130
    except _ConfigurationError as exc:
        _report_error("runtime configuration is invalid", exc)
        return 2
    except Exception as exc:
        _report_error("runtime failure", exc)
        return 1


def _report_error(prefix: str, exc: BaseException) -> None:
    try:
        logger.error("{}: {}", prefix, exc)
    except Exception:
        print(f"{prefix}: {exc}", file=sys.stderr)


def _main(args) -> int:
    setup_logger("INFO")
    cancellation = CancellationToken()
    events = LoggingEventSink(logger)

    if args.replay is not None:
        if not args.replay.is_dir() or not os.access(args.replay, os.R_OK):
            _report_error("replay directory is missing or unreadable", args.replay)
            return 2
        try:
            paths = sorted(path for path in args.replay.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"})
        except OSError as exc:
            _report_error("unable to read replay directory", exc)
            return 2
        if not paths:
            _report_error("replay directory contains no PNG/JPG images", args.replay)
            return 2
        if args.frames is not None and args.frames > len(paths):
            _report_error("requested frames exceed replay images", RuntimeError(f"{args.frames} > {len(paths)}"))
            return 2
        source = ReplayCaptureSource(paths)
        serial = "replay"
        connection_generation = lambda: 0
        max_frames = args.frames if args.frames is not None else len(paths)
    else:
        session = DeviceSession(args.device)
        source = ADBCaptureSource(session)
        serial = session.serial
        connection_generation = lambda: session.connection_generation
        max_frames = args.frames

    try:
        perception = LegacyVisionAdapter()
        settings = RuntimeSettings(args.interval)
    except (FileNotFoundError, TypeError, ValueError) as exc:
        raise _ConfigurationError(str(exc)) from exc

    capture = CaptureManager(source, device_serial=serial, connection_generation=connection_generation)
    runtime = BotRuntime(capture=capture, perception=perception, events=events, lifecycle=Lifecycle(), cancellation=cancellation, settings=settings)

    logger.warning("OBSERVE-ONLY: no taps or swipes can be sent by this runtime")
    processed = runtime.run(max_frames=max_frames)
    logger.info("processed {} frames", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
