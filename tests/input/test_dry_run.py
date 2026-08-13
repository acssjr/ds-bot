from src.core.events import EventBus, EventKind
from src.geometry.models import PixelPoint
from src.input.dry_run import DryRunInput
from src.input.models import InputStatus, TapCommand


def test_dry_run_records_command_without_a_device_dependency() -> None:
    bus = EventBus()
    backend = DryRunInput(events=bus, clock=lambda: 12.0)
    command = TapCommand(command_id="tap-1", point=PixelPoint(10, 20), hold_ms=30)

    receipt = backend.execute(command)

    assert receipt.status is InputStatus.DRY_RUN
    assert receipt.backend == "dry_run"
    assert backend.commands == [command]
    events = bus.drain()
    assert len(events) == 1
    assert events[0].kind is EventKind.INPUT
    assert events[0].payload["command_id"] == "tap-1"
