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
        if not isinstance(serial, str):
            raise TypeError("serial must be a string")
        if not serial or not serial.strip():
            raise ValueError("an explicit serial is required")
        self._serial = serial.strip()
        self._adb = adb_client if adb_client is not None else adbutils.adb
        self._device: Any = None
        self._connection_generation = 0

    @property
    def serial(self) -> str:
        return self._serial

    @property
    def connection_generation(self) -> int:
        return self._connection_generation

    @property
    def connected(self) -> bool:
        return self._device is not None

    def connect(self) -> None:
        self._device = None
        try:
            devices = self._adb.device_list()
        except Exception as exc:
            raise DeviceSessionError(
                f"failed to enumerate devices for {self._serial!r}"
            ) from exc

        candidate = next(
            (device for device in devices if device.serial == self._serial), None
        )
        if candidate is None:
            available = {device.serial for device in devices}
            raise DeviceNotFound(
                f"requested device {self._serial!r} is unavailable; found {sorted(available)!r}"
            )
        self._device = candidate
        self._connection_generation += 1

    def disconnect(self) -> None:
        self._device = None

    def _require_device(self):
        if self._device is None:
            raise DeviceNotConnected(f"device {self._serial!r} is not connected")
        return self._device

    def _invoke(self, operation: str, method_name: str, *args, **kwargs):
        try:
            return getattr(self._require_device(), method_name)(*args, **kwargs)
        except DeviceNotConnected:
            raise
        except Exception as exc:
            raise DeviceSessionError(
                f"ADB operation {operation!r} failed for {self._serial!r}"
            ) from exc

    def screenshot(self):
        return self._invoke("screenshot", "screenshot", error_ok=False)

    def click(self, x: int, y: int) -> None:
        self._invoke("click", "click", x, y)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_seconds: float) -> None:
        self._invoke("swipe", "swipe", x1, y1, x2, y2, duration_seconds)

    def shell(self, command: str) -> str:
        result = self._invoke("shell", "shell", command)
        if not isinstance(result, str):
            raise DeviceSessionError(
                f"unexpected shell result for {self._serial!r}: {type(result).__name__}"
            )
        return result

    def stop_app(self, package_name: str) -> None:
        self._invoke("stop_app", "app_stop", package_name)

    def start_app(self, package_name: str) -> None:
        self._invoke("start_app", "app_start", package_name)
