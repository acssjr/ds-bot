from dataclasses import dataclass

import pytest

from src.automation.game_launcher import GameLauncher, GameLaunchTimeout
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind


@dataclass
class App:
    package: str
    activity: str = "MainActivity"


class Session:
    serial = "MEmu"

    def __init__(self, packages: list[str]) -> None:
        self.connected = False
        self.packages = iter(packages)
        self.current = "com.microvirt.launcher"
        self.started: list[str] = []

    def connect(self) -> None:
        self.connected = True

    def foreground_app(self) -> App:
        try:
            self.current = next(self.packages)
        except StopIteration:
            pass
        return App(self.current)

    def start_app(self, package: str) -> None:
        self.started.append(package)


def test_launcher_opens_game_from_memu_home_and_reports_ready() -> None:
    session = Session(["com.microvirt.launcher", "com.QuestLab.DraftWar"])
    events = EventBus(capacity=16)
    launcher = GameLauncher(session, events=events, poll_seconds=0.001)

    result = launcher.ensure_foreground(CancellationToken())

    assert result.started is True
    assert session.started == ["com.QuestLab.DraftWar"]
    statuses = [event.payload["status"] for event in events.drain()]
    assert statuses == ["connecting", "launching", "ready"]


def test_launcher_does_not_restart_game_already_in_foreground() -> None:
    session = Session(["com.QuestLab.DraftWar"])
    result = GameLauncher(session).ensure_foreground(CancellationToken())
    assert result.started is False
    assert session.started == []


def test_launcher_timeout_never_generates_gameplay_input() -> None:
    session = Session(["com.microvirt.launcher"])
    ticks = iter([0.0, 0.0, 1.0, 2.0, 3.0])
    launcher = GameLauncher(
        session,
        timeout_seconds=0.5,
        poll_seconds=0.001,
        clock=ticks.__next__,
    )
    with pytest.raises(GameLaunchTimeout):
        launcher.ensure_foreground(CancellationToken())
    assert session.started == ["com.QuestLab.DraftWar"]
