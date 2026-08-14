from __future__ import annotations

import time
from collections.abc import Callable

from src.core.events import EventKind, EventSink, RuntimeEvent
from src.device.session import DeviceSession
from src.input.models import InputReceipt, InputStatus, TapCommand


class InputCommitUnknown(RuntimeError):
    """ADB failed after invocation; whether Android received the tap is unknown."""

    def __init__(self, receipt: InputReceipt, cause: BaseException) -> None:
        super().__init__(receipt.detail)
        self.receipt = receipt
        self.__cause__ = cause


class LiveAdbInput:
    def __init__(
        self,
        *,
        session: DeviceSession,
        events: EventSink,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._events = events
        self._clock = clock

    def _publish(self, receipt: InputReceipt, command: TapCommand) -> None:
        try:
            self._events.publish(
                RuntimeEvent(
                    EventKind.INPUT,
                    receipt.completed_at_monotonic,
                    {
                        "command_id": receipt.command_id,
                        "status": receipt.status.value,
                        "backend": receipt.backend,
                        "point": command.point.as_tuple(),
                        "started_at_monotonic": receipt.started_at_monotonic,
                        "completed_at_monotonic": receipt.completed_at_monotonic,
                        "detail": receipt.detail,
                    },
                )
            )
        except Exception:
            # Telemetry must never turn a committed tap into an apparent retry.
            pass

    def execute(self, command: TapCommand) -> InputReceipt:
        if not isinstance(command, TapCommand):
            raise TypeError("command must be a TapCommand")
        started = self._clock()
        try:
            self._session.click(command.point.x, command.point.y)
        except Exception as exc:
            receipt = InputReceipt(
                command_id=command.command_id,
                status=InputStatus.COMMIT_UNKNOWN,
                backend="adb",
                started_at_monotonic=started,
                completed_at_monotonic=self._clock(),
                detail="ADB tap failed after invocation; commit status is unknown",
            )
            self._publish(receipt, command)
            raise InputCommitUnknown(receipt, exc) from exc

        receipt = InputReceipt(
            command_id=command.command_id,
            status=InputStatus.SENT,
            backend="adb",
            started_at_monotonic=started,
            completed_at_monotonic=self._clock(),
            detail="tap sent; visual postcondition pending",
        )
        self._publish(receipt, command)
        return receipt
