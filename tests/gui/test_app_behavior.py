from __future__ import annotations

import queue
from collections.abc import Callable

import pytest

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
    daemon = True

    def is_alive(self) -> bool:
        return True

    def join(self, _timeout: float | None = None) -> None:
        raise AssertionError("GUI close must not join the worker")


class CancelAwareThread:
    daemon = True

    def __init__(self, cancellation: CancellationToken) -> None:
        self.cancellation = cancellation
        self.join_timeouts: list[float | None] = []

    def is_alive(self) -> bool:
        return not self.cancellation.cancelled

    def join(self, timeout: float | None = None) -> None:
        self.join_timeouts.append(timeout)


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
    gui._serial_by_label = {"emulator-1": "emulator-1"}
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
    gui._dataset_saved_count = 0
    gui._dataset_session_directory = "-"
    gui._session_started_at = None
    gui._observations_total = 0
    gui._unknown_total = 0
    gui._screen_transitions = 0
    gui._current_screen = None
    gui._current_screen_since = None
    gui._clock = gui_app.time.monotonic
    gui._close_deadline = None
    gui._close_finalized = False
    gui.device_option = FakeWidget("device", value="emulator-1", timeline=timeline)
    gui.status_badge = FakeWidget("status", timeline=timeline)
    gui.btn_start = FakeWidget("start", timeline=timeline)
    gui.btn_pause = FakeWidget("pause", timeline=timeline)
    gui.btn_stop = FakeWidget("stop", timeline=timeline)
    gui.btn_refresh = FakeWidget("refresh", timeline=timeline)
    gui.lbl_current_state = FakeWidget("observation", timeline=timeline)
    gui.lbl_context_state = FakeWidget("context", timeline=timeline)
    gui.lbl_session_state = FakeWidget("session", timeline=timeline)
    gui.lbl_capture_state = FakeWidget("capture", timeline=timeline)
    gui.lbl_dataset_state = FakeWidget("dataset", timeline=timeline)
    gui.lbl_resources_primary = FakeWidget("resources-primary", timeline=timeline)
    gui.lbl_resources_progress = FakeWidget("resources-progress", timeline=timeline)
    gui.lbl_resources_collection = FakeWidget("resources-collection", timeline=timeline)
    gui.lbl_resources_status = FakeWidget("resources-status", timeline=timeline)
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


def test_observation_panel_reports_session_coverage_and_transitions() -> None:
    gui = make_headless_gui()
    gui._clock = iter([10.0, 12.5]).__next__
    gui._session_started_at = 9.0

    gui._apply_runtime_event(
        RuntimeEvent(EventKind.OBSERVATION, 1.0, {"screen": "HOME", "confidence": 0.9})
    )
    gui._apply_runtime_event(
        RuntimeEvent(EventKind.OBSERVATION, 2.0, {"screen": "UNKNOWN", "confidence": 0.1})
    )

    text = str(gui.lbl_session_state.options["text"])
    assert "Observações: 2" in text
    assert "Transições: 1" in text
    assert "UNKNOWN: 1 (50.0%)" in text


def test_observation_updates_persistent_account_resources() -> None:
    gui = make_headless_gui()

    gui._apply_runtime_event(
        RuntimeEvent(
            EventKind.OBSERVATION,
            1.0,
            {
                "screen": "HOME",
                "confidence": 0.99,
                "resource_ocr_status": "fresh",
                "resources": {
                    "energy_current": 140,
                    "energy_capacity": 150,
                    "gems": 125,
                    "coins": 3578,
                    "mastery_currency": 26,
                    "trophies": 489,
                    "player_level": 6,
                    "league": "Bronze",
                    "league_rank": 4,
                    "league_points": 108,
                    "collection_unlocked": 9,
                    "collection_total": 25,
                    "units": ({"name": "Cavaleiro", "level": 3},),
                    "resource_confidence": 0.98,
                },
            },
        )
    )

    assert "Energia: 140/150" in str(gui.lbl_resources_primary.options["text"])
    assert "Maestria: 26 M" in str(gui.lbl_resources_primary.options["text"])
    assert "Troféus: 489" in str(gui.lbl_resources_progress.options["text"])
    assert "Posição: #4" in str(gui.lbl_resources_progress.options["text"])
    assert "Cavaleiro Nv.3" in str(gui.lbl_resources_collection.options["text"])


def test_ad_context_never_presents_pending_reward_as_safe_to_close() -> None:
    gui = make_headless_gui()

    gui._apply_runtime_event(
        RuntimeEvent(
            EventKind.OBSERVATION,
            1.0,
            {
                "screen": "WATCHING_AD",
                "confidence": 0.9,
                "context": "rewarded_ad",
                "safe_to_close": False,
            },
        )
    )

    assert "Fechamento seguro: NÃO" in str(gui.lbl_context_state.options["text"])

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


def test_discovery_auto_selects_the_only_available_device() -> None:
    gui = make_headless_gui()
    gui.is_running = False
    gui._available_serials = ()
    gui._discovery_results.put_nowait(
        gui_app.DeviceDiscoveryResult(
            serials=("127.0.0.1:21503",),
            labels=("MEmu · 127.0.0.1:21503",),
        )
    )

    gui._process_discovery_results()

    assert gui._available_serials == ("127.0.0.1:21503",)
    assert gui.device_option.options["values"] == [
        gui_app.DEVICE_SELECTION_PLACEHOLDER,
        "MEmu · 127.0.0.1:21503",
    ]
    assert gui.device_option.value == "MEmu · 127.0.0.1:21503"
    assert gui.btn_start.options["state"] == "normal"


def test_discovery_keeps_explicit_selection_when_multiple_devices_exist() -> None:
    gui = make_headless_gui()
    gui.is_running = False
    gui._available_serials = ()
    serials = ("emulator-1", "emulator-2")
    gui._discovery_results.put_nowait(gui_app.DeviceDiscoveryResult(serials=serials))

    gui._process_discovery_results()

    assert gui.device_option.value == gui_app.DEVICE_SELECTION_PLACEHOLDER
    assert gui.btn_start.options["state"] == "disabled"
    gui.device_option.set(serials[-1])
    gui._on_device_selected(serials[-1])

    assert gui.btn_start.options["state"] == "normal"


def test_device_placeholder_cannot_start_observation() -> None:
    gui = make_headless_gui()
    gui.is_running = False
    gui.device_option.set(gui_app.DEVICE_SELECTION_PLACEHOLDER)

    def forbidden_factory(**_kwargs: object) -> StartFailingThread:
        raise AssertionError("placeholder must not create a worker")

    gui._thread_factory = forbidden_factory

    gui.start_observation()

    assert gui.is_running is False
    assert gui._bot_thread is None


def test_controls_keep_refresh_disabled_while_worker_reference_is_active() -> None:
    gui = make_headless_gui()
    gui.is_running = False
    gui._bot_thread = AliveThread()

    gui._update_controls()

    assert gui.btn_start.options["state"] == "disabled"
    assert gui.btn_refresh.options["state"] == "disabled"


def test_close_waits_for_cancelled_worker_then_joins_and_destroys() -> None:
    cancellation = CancellationToken()
    gui = make_headless_gui(cancellation=cancellation)
    worker = CancelAwareThread(cancellation)
    gui._bot_thread = worker
    gui._log_sink_id = None
    destroyed: list[bool] = []
    gui.destroy = lambda: destroyed.append(True)

    gui._on_close()

    assert cancellation.cancelled is True
    assert worker.join_timeouts == [0]
    assert gui._bot_thread is None
    assert destroyed == [True]


def test_close_with_live_worker_schedules_poll_without_blocking() -> None:
    cancellation = CancellationToken()
    gui = make_headless_gui(cancellation=cancellation)
    gui._bot_thread = AliveThread()
    gui._log_sink_id = None
    scheduled: list[tuple[int, Callable[[], None]]] = []
    gui.after = lambda delay, callback: scheduled.append((delay, callback))
    destroyed: list[bool] = []
    gui.destroy = lambda: destroyed.append(True)

    gui._on_close()

    assert cancellation.cancelled is True
    assert gui._closing is True
    assert gui.status_badge.options["text"] == "🟠 ENCERRANDO"
    assert gui.btn_start.options["state"] == "disabled"
    assert gui.btn_stop.options["state"] == "disabled"
    assert scheduled and scheduled[0][0] == gui_app.CLOSE_POLL_MS
    assert destroyed == []


def test_close_deadline_uses_daemon_fallback_and_destroys() -> None:
    now = [10.0]
    cancellation = CancellationToken()
    gui = make_headless_gui(cancellation=cancellation)
    gui._clock = lambda: now[0]
    gui._bot_thread = AliveThread()
    gui._log_sink_id = None
    scheduled: list[tuple[int, Callable[[], None]]] = []
    gui.after = lambda delay, callback: scheduled.append((delay, callback))
    destroyed: list[bool] = []
    gui.destroy = lambda: destroyed.append(True)

    gui._on_close()
    now[0] = 10.0 + gui_app.CLOSE_TIMEOUT_SECONDS
    scheduled.pop()[1]()

    assert destroyed == [True]
    assert gui._close_finalized is True


def test_close_without_worker_destroys_even_if_log_sink_removal_fails() -> None:
    cancellation = CancellationToken()
    gui = make_headless_gui(cancellation=cancellation)
    gui._bot_thread = None
    gui._log_sink_id = 2_147_483_647
    destroyed: list[bool] = []
    gui.destroy = lambda: destroyed.append(True)

    gui._on_close()
    gui._on_close()

    assert cancellation.cancelled is True
    assert gui._closing is True
    assert gui._log_sink_id is None
    assert destroyed == [True]
