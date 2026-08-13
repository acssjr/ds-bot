from __future__ import annotations

from enum import Enum


class RuntimeStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    FAILED = "failed"


class InvalidLifecycleTransition(RuntimeError):
    pass


_ALLOWED = {
    RuntimeStatus.STOPPED: {RuntimeStatus.STARTING},
    RuntimeStatus.STARTING: {RuntimeStatus.RUNNING, RuntimeStatus.STOPPING, RuntimeStatus.FAILED},
    RuntimeStatus.RUNNING: {RuntimeStatus.PAUSED, RuntimeStatus.STOPPING, RuntimeStatus.FAILED},
    RuntimeStatus.PAUSED: {RuntimeStatus.RUNNING, RuntimeStatus.STOPPING, RuntimeStatus.FAILED},
    RuntimeStatus.STOPPING: {RuntimeStatus.STOPPED, RuntimeStatus.FAILED},
    RuntimeStatus.FAILED: {RuntimeStatus.STOPPED},
}


class Lifecycle:
    def __init__(self) -> None:
        self._status = RuntimeStatus.STOPPED

    @property
    def status(self) -> RuntimeStatus:
        return self._status

    def transition(self, target: RuntimeStatus) -> None:
        if target not in _ALLOWED[self._status]:
            raise InvalidLifecycleTransition(f"cannot transition from {self._status} to {target}")
        self._status = target
