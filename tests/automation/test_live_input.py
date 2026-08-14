from src.automation.live_input import InputCommitUnknown, LiveAdbInput
from src.core.events import EventBus, EventKind
from src.geometry.models import PixelPoint
from src.input.models import InputStatus, TapCommand


class FakeSession:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.clicks: list[tuple[int, int]] = []

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))
        if self.failure is not None:
            raise self.failure


def test_live_input_sends_exact_tap_and_publishes_receipt() -> None:
    session = FakeSession()
    events = EventBus(capacity=4)
    ticks = iter([1.0, 1.1])
    backend = LiveAdbInput(session=session, events=events, clock=ticks.__next__)  # type: ignore[arg-type]

    receipt = backend.execute(TapCommand("tap-1", PixelPoint(616, 432)))

    assert session.clicks == [(616, 432)]
    assert receipt.status is InputStatus.SENT
    event = events.drain()[0]
    assert event.kind is EventKind.INPUT
    assert event.payload["point"] == (616, 432)


def test_ambiguous_adb_failure_is_never_presented_as_safe_to_retry() -> None:
    session = FakeSession(RuntimeError("socket closed"))
    events = EventBus(capacity=4)
    ticks = iter([2.0, 2.1])
    backend = LiveAdbInput(session=session, events=events, clock=ticks.__next__)  # type: ignore[arg-type]

    try:
        backend.execute(TapCommand("tap-2", PixelPoint(10, 20)))
    except InputCommitUnknown as exc:
        assert exc.receipt.status is InputStatus.COMMIT_UNKNOWN
    else:
        raise AssertionError("ambiguous failure must stop the executor")

    assert session.clicks == [(10, 20)]
    assert events.drain()[0].payload["status"] == "commit_unknown"
