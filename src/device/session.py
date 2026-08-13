from __future__ import annotations

from typing import Any

import adbutils


class DeviceSessionError(RuntimeError):
    pass


class DeviceNotFound(DeviceSessionError):
    pass


class DeviceNotConnected(DeviceSessionError):
    pass


class DeviceSession:
    def __init__(self, serial: str, *, adb_client: Any = None):
        if not serial or not serial.strip():
            raise ValueError("an explicit serial is required")
        self.serial = serial.strip()
        self._adb = adb_client if adb_client is not None else adbutils.adb
        self._device: Any = None
        self.connection_generation = 0

    @property
    def connected(self) -> bool:
        return self._device is not None

    def connect(self) -> None:
        available = {device.serial for device in self._adb.device_list()}
        if self.serial not in available:
            raise DeviceNotFound(
                f"requested device {self.serial!r} is unavailable; found {sorted(available)!r}"
            )
        self._device = self._adb.device(serial=self.serial)
        self.connection_generation += 1

    def disconnect(self) -> None:
        self._device = None

    def _require_device(self):
        if self._device is None:
            raise DeviceNotConnected(f"device {self.serial!r} is not connected")
        return self._device

    def screenshot(self):
        return self._require_device().screenshot()

    def click(self, x: int, y: int) -> None:
        self._require_device().click(x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_seconds: float) -> None:
        self._require_device().swipe(x1, y1, x2, y2, duration_seconds)

    def shell(self, command: str) -> str:
        return str(self._require_device().shell(command))

    def stop_app(self, package_name: str) -> None:
        self._require_device().app_stop(package_name)

    def start_app(self, package_name: str) -> None:
        self._require_device().app_start(package_name)
