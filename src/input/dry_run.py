from __future__ import annotations

import time
import threading
from collections.abc import Callable

from src.core.events import EventBus, EventKind, RuntimeEvent
from src.input.models import InputReceipt, InputStatus, TapCommand


class DryRunInput:
    def __init__(self, *, events: EventBus, clock: Callable[[], float] = time.monotonic):
        self._events = events
        self._clock = clock
        self._commands: list[TapCommand] = []
        self._lock = threading.Lock()

    @property
    def commands(self) -> tuple[TapCommand, ...]:
        with self._lock:
            return tuple(self._commands)

    def execute(self, command: TapCommand) -> InputReceipt:
        if not isinstance(command, TapCommand):
            raise TypeError("command must be a TapCommand")
        started = self._clock()
        completed = self._clock()
        receipt = InputReceipt(
            command_id=command.command_id,
            status=InputStatus.DRY_RUN,
            backend="dry_run",
            started_at_monotonic=started,
            completed_at_monotonic=completed,
            detail="command recorded; no input sent",
        )
        event = RuntimeEvent(
            EventKind.INPUT,
            receipt.completed_at_monotonic,
            {
                "command_id": receipt.command_id,
                "status": receipt.status.value,
                "backend": receipt.backend,
                "started_at_monotonic": receipt.started_at_monotonic,
                "completed_at_monotonic": receipt.completed_at_monotonic,
            },
        )
        with self._lock:
            self._commands.append(command)
            try:
                self._events.publish(event)
            except Exception:
                assert self._commands[-1] is command
                self._commands.pop()
                raise
        return receipt
