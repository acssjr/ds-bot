from dataclasses import dataclass

from src.recovery.app_supervisor import GAME_PACKAGE, RewardedAdAppSupervisor


@dataclass
class App:
    package: str
    activity: str = "Main"


class FakeSession:
    def __init__(self, packages: list[str]) -> None:
        self.packages = iter(packages)
        self.current = ""
        self.back_calls = 0
        self.started: list[str] = []
        self.stopped: list[str] = []

    def foreground_app(self) -> App:
        try:
            self.current = next(self.packages)
        except StopIteration:
            pass
        return App(self.current)

    def press_back(self) -> None:
        self.back_calls += 1

    def start_app(self, package: str) -> None:
        self.started.append(package)

    def stop_app(self, package: str) -> None:
        self.stopped.append(package)


def supervisor(session: FakeSession) -> RewardedAdAppSupervisor:
    return RewardedAdAppSupervisor(
        session,  # type: ignore[arg-type]
        clock=lambda: 10.0,
        check_interval_seconds=0,
        recovery_delay_seconds=0,
        sleeper=lambda _delay: None,
    )


def test_does_not_control_external_app_until_rewarded_ad_was_seen() -> None:
    session = FakeSession(["com.android.chrome"])

    result = supervisor(session).after_observation({"screen": "HOME"})

    assert result is None
    assert session.back_calls == 0


def test_waits_through_multi_part_ad_while_game_remains_foreground() -> None:
    session = FakeSession([GAME_PACKAGE, GAME_PACKAGE])
    recovery = supervisor(session)

    assert recovery.after_observation({"screen": "WATCHING_AD"}) is None
    assert recovery.after_observation({"screen": "WATCHING_AD"}) is None
    assert session.back_calls == 0


def test_returns_from_play_store_with_android_back() -> None:
    session = FakeSession([GAME_PACKAGE, "com.android.vending", GAME_PACKAGE])
    recovery = supervisor(session)
    recovery.after_observation({"screen": "WATCHING_AD"})

    result = recovery.after_observation({"screen": "UNKNOWN"})

    assert result is not None
    assert result["status"] == "recovered"
    assert result["method"] == "android_back"
    assert result["external_package"] == "com.android.vending"
    assert session.back_calls == 1
    assert recovery.after_observation({"screen": "UNKNOWN"}) is None
    assert session.back_calls == 1


def test_restarts_game_only_after_back_and_relaunch_fail() -> None:
    external = "com.android.chrome"
    session = FakeSession(
        [GAME_PACKAGE, external, external, external, external, GAME_PACKAGE]
    )
    recovery = supervisor(session)
    recovery.after_observation({"screen": "WATCHING_AD"})

    result = recovery.after_observation({"screen": "UNKNOWN"})

    assert result is not None
    assert result["method"] == "restart_game"
    assert result["status"] == "recovered"
    assert session.back_calls == 2
    assert session.started == [GAME_PACKAGE, GAME_PACKAGE]
    assert session.stopped == [GAME_PACKAGE]
