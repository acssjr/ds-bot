from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from io import BytesIO
from numbers import Real
from typing import Any

import adbutils
from adbutils._utils import adb_path
from PIL import Image


class DeviceSessionError(RuntimeError):
    pass


class DeviceNotFound(DeviceSessionError):
    pass


class DeviceNotConnected(DeviceSessionError):
    pass


@dataclass(frozen=True, slots=True)
class ForegroundApp:
    package: str
    activity: str


class DeviceSession:
    """Explicit ADB session.

    ``timeout_seconds`` configures socket inactivity timeouts, not an absolute
    wall-clock deadline for a native ADB operation.
    """
    def __init__(self, serial: str, *, adb_client: Any = None, timeout_seconds: float = 10.0):
        if not isinstance(serial, str):
            raise TypeError("serial must be a string")
        if not serial or not serial.strip():
            raise ValueError("an explicit serial is required")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, Real):
            raise TypeError("timeout_seconds must be a real number")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._serial = serial.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._adb = adb_client if adb_client is not None else adbutils.AdbClient(socket_timeout=self._timeout_seconds)
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

    def reconnect(self) -> None:
        """Refresh the adbutils device handle without restarting the ADB server."""
        self.disconnect()
        self.connect()

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

    def foreground_app(self) -> ForegroundApp:
        current = self._invoke("foreground_app", "app_current")
        package = str(getattr(current, "package", "") or "").strip()
        activity = str(getattr(current, "activity", "") or "").strip()
        if not package:
            raise DeviceSessionError(
                f"ADB returned no foreground package for {self._serial!r}"
            )
        return ForegroundApp(package=package, activity=activity)

    def press_back(self) -> None:
        self._invoke("press_back", "keyevent", "BACK")

    def screencap_png(self) -> Image.Image:
        try:
            payload = self._invoke(
                "screencap",
                "shell",
                ["screencap", "-p"],
                encoding=None,
                timeout=self._timeout_seconds,
            )
            if not isinstance(payload, bytes):
                raise TypeError(f"unexpected screencap result: {type(payload).__name__}")
            image = Image.open(BytesIO(payload))
            image.load()
            return image
        except DeviceSessionError:
            raise
        except Exception as exc:
            raise DeviceSessionError(f"ADB operation 'screencap' failed for {self._serial!r}") from exc

    def screencap_exec_out_png(self) -> Image.Image:
        """Capture through native ``adb exec-out`` (more reliable on MEmu)."""
        self._require_device()
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                [adb_path(), "-s", self._serial, "exec-out", "screencap", "-p"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self._timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )
            if result.returncode != 0:
                detail = result.stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(detail or f"adb exited with {result.returncode}")
            image = Image.open(BytesIO(result.stdout))
            image.load()
            return image
        except DeviceNotConnected:
            raise
        except Exception as exc:
            raise DeviceSessionError(
                f"ADB operation 'exec-out screencap' failed for {self._serial!r}"
            ) from exc

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
