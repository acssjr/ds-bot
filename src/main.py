from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.capture.replay import ReplayCaptureSource
from src.core.cancellation import CancellationToken
from src.core.events import EventBus
from src.core.lifecycle import Lifecycle
from src.device.session import DeviceSession
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.utils.logging_config import setup_logger
from src.vision.legacy_adapter import LegacyVisionAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft Showdown observe-only runtime")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--device", help="explicit ADB serial, for example 127.0.0.1:21503")
    source.add_argument("--replay", type=Path, help="directory containing replay PNG/JPG files")
    parser.add_argument("--frames", type=int, default=None, help="stop after this many frames")
    parser.add_argument("--interval", type=float, default=0.25, help="seconds between frames")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logger("INFO")
    cancellation = CancellationToken()
    events = EventBus()

    if args.replay is not None:
        paths = sorted(path for path in args.replay.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"})
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

    capture = CaptureManager(source, device_serial=serial, connection_generation=connection_generation)
    runtime = BotRuntime(
        capture=capture,
        perception=LegacyVisionAdapter(),
        events=events,
        lifecycle=Lifecycle(),
        cancellation=cancellation,
        settings=RuntimeSettings(args.interval),
    )

    logger.warning("OBSERVE-ONLY: no taps or swipes can be sent by this runtime")
    try:
        processed = runtime.run(max_frames=max_frames)
    except KeyboardInterrupt:
        cancellation.cancel()
        return 130
    finally:
        for event in events.drain():
            logger.info("{} | {}", event.kind.value, dict(event.payload))
    logger.info("processed {} frames", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
