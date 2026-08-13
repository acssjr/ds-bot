from __future__ import annotations

import time
from collections.abc import Callable

from src.core.events import EventBus, EventKind, RuntimeEvent
from src.input.models import InputReceipt, InputStatus, TapCommand


class DryRunInput:
    def __init__(self, *, events: EventBus, clock: Callable[[], float] = time.monotonic):
        self._events = events
        self._clock = clock
        self.commands: list[TapCommand] = []

    def execute(self, command: TapCommand) -> InputReceipt:
        started = self._clock()
        self.commands.append(command)
        receipt = InputReceipt(
            command_id=command.command_id,
            status=InputStatus.DRY_RUN,
            backend="dry_run",
            started_at_monotonic=started,
            completed_at_monotonic=self._clock(),
            detail="command recorded; no input sent",
        )
        self._events.publish(
            RuntimeEvent(
                EventKind.INPUT,
                receipt.completed_at_monotonic,
                {"command_id": command.command_id, "status": receipt.status.value},
            )
        )
        return receipt
