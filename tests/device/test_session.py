import pytest

from src.device.session import DeviceNotFound, DeviceSession


class FakeDevice:
    def __init__(self, serial: str):
        self.serial = serial
        self.clicks: list[tuple[int, int]] = []

    def screenshot(self):
        return "image"

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))


class FakeAdbClient:
    def __init__(self, serials: list[str]):
        self.devices = {serial: FakeDevice(serial) for serial in serials}

    def device_list(self):
        return list(self.devices.values())

    def device(self, serial: str):
        return self.devices[serial]


def test_session_requires_an_explicit_serial() -> None:
    with pytest.raises(ValueError, match="explicit serial"):
        DeviceSession("", adb_client=FakeAdbClient(["A"]))


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
