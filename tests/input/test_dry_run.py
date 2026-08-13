import math
from dataclasses import FrozenInstanceError

import pytest

from src.core.events import EventBus, EventKind
from src.geometry.models import PixelPoint
from src.input.dry_run import DryRunInput
from src.input.models import InputReceipt, InputStatus, TapCommand


def valid_receipt_kwargs() -> dict:
    return {
        "command_id": "tap-1",
        "status": InputStatus.DRY_RUN,
        "backend": "dry_run",
        "started_at_monotonic": 1.0,
        "completed_at_monotonic": 2.0,
        "detail": "recorded",
    }


def test_dry_run_records_command_without_a_device_dependency() -> None:
    bus = EventBus()
    backend = DryRunInput(events=bus, clock=lambda: 12.0)
    command = TapCommand(command_id="tap-1", point=PixelPoint(10, 20), hold_ms=30)

    receipt = backend.execute(command)

    assert receipt.command_id == "tap-1"
    assert receipt.status is InputStatus.DRY_RUN
    assert receipt.backend == "dry_run"
    assert receipt.started_at_monotonic == 12.0
    assert receipt.completed_at_monotonic == 12.0
    assert receipt.detail == "command recorded; no input sent"
    assert backend.commands == (command,)
    events = bus.drain()
    assert len(events) == 1
    assert events[0].kind is EventKind.INPUT
    assert events[0].payload["command_id"] == "tap-1"
    assert events[0].payload["status"] == "dry_run"
    assert events[0].payload["backend"] == "dry_run"
    assert events[0].payload["started_at_monotonic"] == 12.0
    assert events[0].payload["completed_at_monotonic"] == 12.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command_id", ""), ("command_id", "   "), ("command_id", 1),
        ("point", (1, 2)),
        ("hold_ms", True), ("hold_ms", 0), ("hold_ms", -1), ("hold_ms", 1.5),
    ],
)
def test_tap_command_rejects_invalid_fields(field, value) -> None:
    kwargs = {"command_id": "tap-1", "point": PixelPoint(1, 2), "hold_ms": 30}
    kwargs[field] = value
    with pytest.raises((TypeError, ValueError)):
        TapCommand(**kwargs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command_id", ""), ("command_id", 1),
        ("status", "dry_run"),
        ("backend", ""), ("backend", 1),
        ("started_at_monotonic", True), ("started_at_monotonic", -1.0),
        ("started_at_monotonic", math.nan), ("started_at_monotonic", math.inf),
        ("completed_at_monotonic", True), ("completed_at_monotonic", -1.0),
        ("completed_at_monotonic", math.nan), ("completed_at_monotonic", math.inf),
        ("completed_at_monotonic", 0.5),
        ("detail", None),
    ],
)
def test_input_receipt_rejects_invalid_fields(field, value) -> None:
    kwargs = valid_receipt_kwargs()
    kwargs[field] = value
    with pytest.raises((TypeError, ValueError)):
        InputReceipt(**kwargs)


def test_input_models_are_frozen() -> None:
    command = TapCommand("tap-1", PixelPoint(1, 2))
    receipt = InputReceipt(**valid_receipt_kwargs())
    with pytest.raises(FrozenInstanceError):
        command.command_id = "other"
    with pytest.raises(FrozenInstanceError):
        receipt.backend = "other"


class SequenceClock:
    def __init__(self, values):
        self._values = iter(values)

    def __call__(self):
        value = next(self._values)
        if isinstance(value, Exception):
            raise value
        return value


class FailingEventBus(EventBus):
    def publish(self, event):
        raise RuntimeError("publish failed")


def test_execute_requires_tap_command() -> None:
    backend = DryRunInput(events=EventBus(), clock=lambda: 1.0)
    with pytest.raises(TypeError, match="TapCommand"):
        backend.execute(object())


@pytest.mark.parametrize(
    "clock_values",
    [
        [1.0, RuntimeError("clock failed")],
        [1.0, math.nan],
        [2.0, 1.0],
    ],
)
def test_execute_failure_does_not_leave_partial_history(clock_values) -> None:
    bus = EventBus()
    backend = DryRunInput(events=bus, clock=SequenceClock(clock_values))
    command = TapCommand("tap-1", PixelPoint(1, 2))
    with pytest.raises((RuntimeError, ValueError)):
        backend.execute(command)
    assert backend.commands == ()
    assert bus.drain() == []


def test_publish_failure_rolls_back_command_history() -> None:
    backend = DryRunInput(events=FailingEventBus(), clock=lambda: 1.0)
    with pytest.raises(RuntimeError, match="publish failed"):
        backend.execute(TapCommand("tap-1", PixelPoint(1, 2)))
    assert backend.commands == ()


def test_command_history_is_an_immutable_snapshot() -> None:
    backend = DryRunInput(events=EventBus(), clock=lambda: 1.0)
    command = TapCommand("tap-1", PixelPoint(1, 2))
    backend.execute(command)
    snapshot = backend.commands
    assert snapshot == (command,)
    assert isinstance(snapshot, tuple)


def test_input_package_has_no_live_device_dependencies() -> None:
    from pathlib import Path

    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/input").glob("*.py"))
    for forbidden in ("adbutils", "DeviceSession", "ADBController", ".click(", ".swipe("):
        assert forbidden not in source
