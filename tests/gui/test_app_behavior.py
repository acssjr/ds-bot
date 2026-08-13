from __future__ import annotations

import queue
from collections.abc import Callable

from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind, RuntimeEvent
from src.core.lifecycle import Lifecycle
from src.gui import app as gui_app
from src.gui.app import DraftShowdownGUI, run_observer_worker
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings


class FakeWidget:
    def __init__(
        self,
        name: str,
        *,
        value: str = "",
        timeline: list[tuple[str, dict[str, object]]] | None = None,
    ) -> None:
        self.name = name
        self.value = value
        self.options: dict[str, object] = {}
        self.timeline = timeline if timeline is not None else []

    def configure(self, **kwargs: object) -> None:
        self.options.update(kwargs)
        self.timeline.append((self.name, dict(kwargs)))

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class PublishingDeadThread:
    def __init__(self, publish_on_death: Callable[[], None]) -> None:
        self._publish_on_death = publish_on_death
        self._published = False
        self.join_timeouts: list[float | None] = []

    def is_alive(self) -> bool:
        if not self._published:
            self._publish_on_death()
            self._published = True
        return False

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)


class FakeTextbox:
    def __init__(self) -> None:
        self.inserted: list[str] = []
        self.deleted: list[tuple[str, str]] = []
        self.see_calls = 0

    def insert(self, _index: str, message: str) -> None:
        self.inserted.append(message)

    def delete(self, start: str, end: str) -> None:
        self.deleted.append((start, end))

    def see(self, _index: str) -> None:
        self.see_calls += 1


class StartFailingThread:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def start(self) -> None:
        raise RuntimeError("thread start failed")

    def is_alive(self) -> bool:
        return False


class AliveThread:
    def is_alive(self) -> bool:
        return True

    def join(self, _timeout: float | None = None) -> None:
        raise AssertionError("GUI close must not join the worker")


class FailingCapture:
    def start(self) -> None:
        pass

    def next_frame(self, _request: object) -> object:
        raise RuntimeError("capture failed")

    def stop(self) -> None:
        pass


class UnusedPerception:
    def analyze(self, _image: object) -> dict[str, object]:
        raise AssertionError("capture failure must happen before perception")


def make_headless_gui(
    *,
    events: EventBus | None = None,
    cancellation: CancellationToken | None = None,
    timeline: list[tuple[str, dict[str, object]]] | None = None,
) -> DraftShowdownGUI:
    gui = DraftShowdownGUI.__new__(DraftShowdownGUI)
    gui._closing = False
    gui.is_running = True
    gui._available_serials = ("emulator-1",)
    gui._runtime_events = events
    gui._cancellation = cancellation
    gui._thread_factory = gui_app.threading.Thread
    gui._bot_thread = None
    gui._discovery_thread = None
    gui._discovery_results = queue.Queue(maxsize=1)
    gui._last_lifecycle_key = None
    gui._last_lifecycle_status = None
    gui._last_error_text = None
    gui._reported_dropped_events = 0
    gui.device_option = FakeWidget("device", value="emulator-1", timeline=timeline)
    gui.status_badge = FakeWidget("status", timeline=timeline)
    gui.btn_start = FakeWidget("start", timeline=timeline)
    gui.btn_pause = FakeWidget("pause", timeline=timeline)
    gui.btn_stop = FakeWidget("stop", timeline=timeline)
    gui.btn_refresh = FakeWidget("refresh", timeline=timeline)
    gui.lbl_current_state = FakeWidget("observation", timeline=timeline)
    gui.after = lambda *_args, **_kwargs: None
    return gui


def test_reaper_consumes_last_error_before_enabling_a_new_session() -> None:
    timeline: list[tuple[str, dict[str, object]]] = []
    events = EventBus(capacity=8)
    cancellation = CancellationToken()
    gui = make_headless_gui(
        events=events,
        cancellation=cancellation,
        timeline=timeline,
    )
    worker = PublishingDeadThread(
        lambda: events.publish(
            RuntimeEvent(
                EventKind.ERROR,
                1.0,
                {"phase": "run", "error": "RuntimeError('capture failed')"},
            )
        )
    )
    gui._bot_thread = worker

    gui._process_runtime_events()

    assert gui._bot_thread is None
    assert gui._runtime_events is None
    assert worker.join_timeouts == [0]
    assert gui.status_badge.options["text"] == "🔴 FALHA"
    assert gui.btn_start.options["state"] == "normal"
    assert events.drain() == []
    assert isinstance(gui._bot_thread, type(None))
    error_index = next(
        index
        for index, (name, options) in enumerate(timeline)
        if name == "status" and options.get("text") == "🔴 FALHA"
    )
    start_index = next(
        index
        for index, (name, options) in enumerate(timeline)
        if name == "start" and options.get("state") == "normal"
    )
    assert error_index < start_index
    assert sum(
        name == "status" and options.get("text") == "🔴 FALHA"
        for name, options in timeline
    ) == 1


def test_new_session_is_rejected_until_dead_worker_is_reaped() -> None:
    gui = make_headless_gui()
    gui.is_running = False
    existing_worker = PublishingDeadThread(lambda: None)
    gui._bot_thread = existing_worker

    def forbidden_factory(**_kwargs: object) -> StartFailingThread:
        raise AssertionError("new worker must not be created before reaping")

    gui._thread_factory = forbidden_factory

    gui.start_observation()

    assert gui._bot_thread is existing_worker


def test_cancelled_worker_without_terminal_lifecycle_is_stopped() -> None:
    cancellation = CancellationToken()
    cancellation.cancel()
    gui = make_headless_gui(
        events=EventBus(capacity=8),
        cancellation=cancellation,
    )
    gui._bot_thread = PublishingDeadThread(lambda: None)

    gui._process_runtime_events()

    assert gui.status_badge.options["text"] == "🔴 PARADO"
    assert gui.btn_start.options["state"] == "normal"


def test_silent_worker_exit_without_terminal_lifecycle_is_failure() -> None:
    gui = make_headless_gui(
        events=EventBus(capacity=8),
        cancellation=CancellationToken(),
    )
    gui._bot_thread = PublishingDeadThread(lambda: None)

    gui._process_runtime_events()

    assert gui.status_badge.options["text"] == "🔴 FALHA"
    assert gui.btn_start.options["state"] == "normal"


def test_log_poller_caps_textbox_history_and_does_not_scroll_when_empty() -> None:
    gui = make_headless_gui()
    gui._log_queue = queue.Queue(maxsize=2)
    gui._log_line_count = 0
    gui.log_textbox = FakeTextbox()
    gui._log_queue.put_nowait("linha\n" * (gui_app.MAX_LOG_LINES + 25))

    gui._process_log_queue()

    assert gui._log_line_count == gui_app.MAX_LOG_LINES
    assert gui.log_textbox.deleted == [("1.0", "26.0")]
    assert gui.log_textbox.see_calls == 1

    gui._process_log_queue()

    assert gui._log_line_count == gui_app.MAX_LOG_LINES
    assert gui.log_textbox.see_calls == 1


def test_runtime_failure_is_not_duplicated_by_gui_worker() -> None:
    events = EventBus(capacity=16)
    cancellation = CancellationToken()

    def runtime_factory(
        _serial: str,
        token: CancellationToken,
        sink: EventBus,
    ) -> BotRuntime:
        return BotRuntime(
            capture=FailingCapture(),  # type: ignore[arg-type]
            perception=UnusedPerception(),
            events=sink,
            lifecycle=Lifecycle(),
            cancellation=token,
            settings=RuntimeSettings(0),
        )

    run_observer_worker(
        "emulator-1",
        cancellation,
        events,
        runtime_factory=runtime_factory,
    )

    errors = [event for event in events.drain() if event.kind is EventKind.ERROR]
    assert len(errors) == 1
    assert errors[0].payload["phase"] == "run"


def test_setup_failure_is_published_once_as_gui_setup() -> None:
    events = EventBus(capacity=16)

    def failing_factory(
        _serial: str,
        _token: CancellationToken,
        _sink: EventBus,
    ) -> BotRuntime:
        raise RuntimeError("templates unavailable")

    run_observer_worker(
        "emulator-1",
        CancellationToken(),
        events,
        runtime_factory=failing_factory,
    )

    errors = [event for event in events.drain() if event.kind is EventKind.ERROR]
    assert len(errors) == 1
    assert errors[0].payload == {
        "phase": "gui-setup",
        "error": "RuntimeError('templates unavailable')",
    }


def test_observation_thread_start_failure_rolls_back_session() -> None:
    created: list[StartFailingThread] = []

    def factory(**kwargs: object) -> StartFailingThread:
        worker = StartFailingThread(**kwargs)
        created.append(worker)
        return worker

    gui = make_headless_gui()
    gui._thread_factory = factory
    gui.is_running = False
    gui._runtime_events = None
    gui._cancellation = None

    gui.start_observation()

    token = created[0].kwargs["args"][1]
    assert isinstance(token, CancellationToken)
    assert token.cancelled is True
    assert gui.is_running is False
    assert gui._bot_thread is None
    assert gui._cancellation is None
    assert gui._runtime_events is None
    assert gui.status_badge.options["text"] == "🔴 FALHA"
    assert gui.btn_start.options["state"] == "normal"
    assert gui.btn_stop.options["state"] == "disabled"
    assert gui.btn_refresh.options["state"] == "normal"


def test_discovery_thread_start_failure_restores_controls() -> None:
    gui = make_headless_gui()
    gui._thread_factory = StartFailingThread
    gui.is_running = False

    gui.refresh_devices()

    assert gui._discovery_thread is None
    assert gui._available_serials == ()
    assert gui.device_option.value == "Falha na busca ADB"
    assert gui.btn_start.options["state"] == "disabled"
    assert gui.btn_refresh.options["state"] == "normal"


def test_controls_keep_refresh_disabled_while_worker_reference_is_active() -> None:
    gui = make_headless_gui()
    gui.is_running = False
    gui._bot_thread = AliveThread()

    gui._update_controls()

    assert gui.btn_start.options["state"] == "disabled"
    assert gui.btn_refresh.options["state"] == "disabled"


def test_close_cancels_and_destroys_even_if_log_sink_removal_fails() -> None:
    cancellation = CancellationToken()
    gui = make_headless_gui(cancellation=cancellation)
    gui._bot_thread = AliveThread()
    gui._log_sink_id = 2_147_483_647
    destroyed: list[bool] = []
    gui.destroy = lambda: destroyed.append(True)

    gui._on_close()

    assert cancellation.cancelled is True
    assert gui._closing is True
    assert gui._log_sink_id is None
    assert destroyed == [True]
