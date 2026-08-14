from pathlib import Path
import random

from src.automation.battle_runner import BattlePhase, BattleRunner, BattleSettings
from src.capture.manager import CaptureManager
from src.capture.replay import ReplayCaptureSource
from src.core.cancellation import CancellationToken
from src.core.events import EventBus
from src.input.dry_run import DryRunInput
from src.vision.pipeline import VisionPipeline


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "live_session"


def test_real_session_frames_drive_one_complete_dry_run_battle() -> None:
    names = [
        "home.jpg",
        "home.jpg",
        "match_intro.jpg",
        "match_intro.jpg",
        "draft_middle_empty.jpg",
        "draft_middle_empty.jpg",
        "combat.jpg",
        "combat.jpg",
        "round_result.jpg",
        "victory_splash.jpg",
        "victory_splash.jpg",
        "victory_mastery.jpg",
        "victory_mastery.jpg",
        "victory_package_ready.jpg",
        "victory_package_ready.jpg",
        "victory_package_animating.jpg",
        "post_battle_offer.jpg",
        "post_battle_offer.jpg",
        "home.jpg",
        "home.jpg",
    ]
    source = ReplayCaptureSource([FIXTURES / name for name in names])
    capture = CaptureManager(
        source,
        device_serial="replay",
        connection_generation=lambda: 0,
    )
    events = EventBus(capacity=32)
    dry_run = DryRunInput(events=events)
    runner = BattleRunner(
        capture=capture,
        perception=VisionPipeline(),
        input_backend=dry_run,
        cancellation=CancellationToken(),
        settings=BattleSettings(0, 0, stable_observations=2),
        rng=random.Random(1),
    )

    result = runner.run()

    assert result.completed is True
    assert result.final_phase is BattlePhase.HOME
    assert result.actions == 6
    assert len(dry_run.commands) == 6
    # Slot 1 is blank in this real frame; the chosen x must be left or right.
    assert dry_run.commands[1].point.x in {round(0.167 * 719), round(0.833 * 719)}
    # The paid offer is closed above mid-screen, never through its purchase button.
    assert dry_run.commands[-1].point.y < 640
