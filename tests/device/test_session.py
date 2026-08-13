from io import BytesIO

from PIL import Image
import pytest

from src.device.session import (
    DeviceNotConnected,
    DeviceNotFound,
    DeviceSession,
    DeviceSessionError,
)


class FakeDevice:
    def __init__(self, serial: str):
        self.serial = serial
        self.clicks: list[tuple[int, int]] = []
        self.swipes: list[tuple[int, int, int, int, float]] = []
        self.shell_commands: list[str] = []
        self.shell_call_options: list[tuple[object, object, object]] = []
        self.stopped_apps: list[str] = []
        self.started_apps: list[str] = []
        self.keyevents: list[str] = []
        self.current_package = "com.QuestLab.DraftWar"
        self.screenshot_error_ok: list[bool] = []
        self.failures: dict[str, Exception] = {}
        self.shell_result: str | bytes = "shell-result"

    def _raise_if_configured(self, operation: str) -> None:
        if failure := self.failures.get(operation):
            raise failure

    def screenshot(self, *, error_ok: bool = True):
        self._raise_if_configured("screenshot")
        self.screenshot_error_ok.append(error_ok)
        return "image"

    def click(self, x: int, y: int) -> None:
        self._raise_if_configured("click")
        self.clicks.append((x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_seconds: float) -> None:
        self._raise_if_configured("swipe")
        self.swipes.append((x1, y1, x2, y2, duration_seconds))

    def shell(self, command, *, encoding="default", timeout=None) -> str | bytes:
        self._raise_if_configured("shell")
        self.shell_commands.append(command)
        self.shell_call_options.append((command, encoding, timeout))
        return self.shell_result

    def app_stop(self, package_name: str) -> None:
        self._raise_if_configured("stop_app")
        self.stopped_apps.append(package_name)

    def app_start(self, package_name: str) -> None:
        self._raise_if_configured("start_app")
        self.started_apps.append(package_name)

    def app_current(self):
        return type(
            "RunningApp",
            (),
            {"package": self.current_package, "activity": "MainActivity"},
        )()

    def keyevent(self, key: str) -> None:
        self.keyevents.append(key)


class FakeAdbClient:
    def __init__(self, serials: list[str]):
        self.devices = {serial: FakeDevice(serial) for serial in serials}
        self.list_error: Exception | None = None
        self.device_calls = 0

    def device_list(self):
        if self.list_error is not None:
            raise self.list_error
        return list(self.devices.values())

    def device(self, serial: str):
        self.device_calls += 1
        return self.devices[serial]


def test_session_requires_an_explicit_serial() -> None:
    with pytest.raises(ValueError, match="explicit serial"):
        DeviceSession("", adb_client=FakeAdbClient(["A"]))


def test_session_requires_a_string_serial() -> None:
    with pytest.raises(TypeError, match="serial must be a string"):
        DeviceSession(123, adb_client=FakeAdbClient(["A"]))


def test_session_binds_only_to_requested_device() -> None:
    client = FakeAdbClient(["A", "B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()
    session.click(10, 20)

    assert session.serial == "B"
    assert session.connection_generation == 1
    assert client.devices["A"].clicks == []
    assert client.devices["B"].clicks == [(10, 20)]


def test_missing_requested_device_is_not_replaced_by_first_device() -> None:
    session = DeviceSession("missing", adb_client=FakeAdbClient(["A", "B"]))
    with pytest.raises(DeviceNotFound, match="missing"):
        session.connect()


def test_screenshot_requires_a_connected_device() -> None:
    session = DeviceSession("B", adb_client=FakeAdbClient(["B"]))

    with pytest.raises(DeviceNotConnected):
        session.screenshot()


def test_disconnect_clears_access_to_the_device() -> None:
    session = DeviceSession("B", adb_client=FakeAdbClient(["B"]))
    session.connect()
    session.disconnect()

    assert session.connected is False
    with pytest.raises(DeviceNotConnected):
        session.screenshot()


def test_failed_reconnection_discards_the_previous_device() -> None:
    client = FakeAdbClient(["B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()
    del client.devices["B"]

    with pytest.raises(DeviceNotFound):
        session.connect()

    assert session.connected is False
    assert session.connection_generation == 1
    with pytest.raises(DeviceNotConnected):
        session.screenshot()


def test_successful_reconnection_uses_the_new_enumerated_device() -> None:
    client = FakeAdbClient(["B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()
    original_device = client.devices["B"]
    replacement_device = FakeDevice("B")
    client.devices["B"] = replacement_device

    session.connect()
    session.click(10, 20)

    assert session.connection_generation == 2
    assert original_device.clicks == []
    assert replacement_device.clicks == [(10, 20)]


def test_session_uses_the_enumerated_device_without_a_second_lookup() -> None:
    client = FakeAdbClient(["B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()

    assert client.device_calls == 0


def test_session_identity_is_read_only() -> None:
    session = DeviceSession("B", adb_client=FakeAdbClient(["B"]))

    with pytest.raises(AttributeError):
        session.serial = "other"
    with pytest.raises(AttributeError):
        session.connection_generation = 2


def test_device_enumeration_errors_preserve_the_original_cause() -> None:
    client = FakeAdbClient(["B"])
    error = RuntimeError("fake list failure")
    client.list_error = error
    session = DeviceSession("B", adb_client=client)

    with pytest.raises(DeviceSessionError, match="enumerate.*B") as caught:
        session.connect()

    assert caught.value.__cause__ is error
    assert session.connected is False
    assert session.connection_generation == 0


def test_screenshot_errors_preserve_the_original_cause() -> None:
    client = FakeAdbClient(["B"])
    error = RuntimeError("fake screenshot failure")
    client.devices["B"].failures["screenshot"] = error
    session = DeviceSession("B", adb_client=client)
    session.connect()

    with pytest.raises(DeviceSessionError, match="screenshot.*B") as caught:
        session.screenshot()

    assert caught.value.__cause__ is error


def test_session_forwards_all_device_operations() -> None:
    client = FakeAdbClient(["B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()

    assert session.screenshot() == "image"
    session.click(1, 2)
    session.swipe(3, 4, 5, 6, 0.7)
    assert session.shell("echo test") == "shell-result"
    session.stop_app("pkg.stop")
    session.start_app("pkg.start")
    session.press_back()
    foreground = session.foreground_app()

    device = client.devices["B"]
    assert device.screenshot_error_ok == [False]
    assert device.clicks == [(1, 2)]
    assert device.swipes == [(3, 4, 5, 6, 0.7)]
    assert device.shell_commands == ["echo test"]
    assert device.stopped_apps == ["pkg.stop"]
    assert device.started_apps == ["pkg.start"]
    assert device.keyevents == ["BACK"]
    assert foreground.package == "com.QuestLab.DraftWar"
    assert foreground.activity == "MainActivity"


def test_reconnect_refreshes_device_handle_and_generation() -> None:
    client = FakeAdbClient(["B"])
    session = DeviceSession("B", adb_client=client)
    session.connect()

    session.reconnect()

    assert session.connected is True
    assert session.connection_generation == 2


def test_shell_rejects_non_string_results() -> None:
    client = FakeAdbClient(["B"])
    client.devices["B"].shell_result = b"shell-result"
    session = DeviceSession("B", adb_client=client)
    session.connect()

    with pytest.raises(DeviceSessionError, match="unexpected shell result.*B"):
        session.shell("echo test")


def test_screencap_uses_dedicated_binary_shell_command_with_timeout() -> None:
    image_bytes = BytesIO()
    Image.new("RGB", (2, 1), (1, 2, 3)).save(image_bytes, format="PNG")
    client = FakeAdbClient(["B"])
    client.devices["B"].shell_result = image_bytes.getvalue()
    session = DeviceSession("B", adb_client=client, timeout_seconds=2.5)
    session.connect()

    image = session.screencap_png()

    assert image.mode == "RGB"
    assert image.size == (2, 1)
    assert client.devices["B"].shell_call_options[-1] == (["screencap", "-p"], None, 2.5)


def test_screencap_errors_preserve_original_cause() -> None:
    client = FakeAdbClient(["B"])
    error = RuntimeError("screencap failed")
    client.devices["B"].failures["shell"] = error
    session = DeviceSession("B", adb_client=client)
    session.connect()

    with pytest.raises(DeviceSessionError, match="screencap.*B") as caught:
        session.screencap_png()
    assert caught.value.__cause__ is error
