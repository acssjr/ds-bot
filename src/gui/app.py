from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import adbutils
import customtkinter as ctk
from loguru import logger

from src.capture.adb_source import ADBCaptureSource
from src.capture.manager import CaptureManager
from src.core.cancellation import CancellationToken
from src.core.events import EventBus, EventKind, RuntimeEvent
from src.core.lifecycle import Lifecycle
from src.device.session import DeviceSession
from src.gui.presenter import (
    format_runtime_error,
    format_runtime_event,
    present_lifecycle,
)
from src.runtime.bot_runtime import BotRuntime, RuntimeSettings
from src.recording.session_recorder import SessionRecorder
from src.recovery.app_supervisor import RewardedAdAppSupervisor
from src.vision.legacy_adapter import LegacyVisionAdapter


EVENT_POLL_MS = 100
LOG_POLL_MS = 150
DISCOVERY_POLL_MS = 100
ADB_SOCKET_TIMEOUT_SECONDS = 5.0
MAX_LOG_LINES = 2000
DEVICE_SELECTION_PLACEHOLDER = "Selecione um dispositivo..."
CLOSE_POLL_MS = 100
CLOSE_TIMEOUT_SECONDS = ADB_SOCKET_TIMEOUT_SECONDS + 1.0


@dataclass(frozen=True, slots=True)
class DeviceDiscoveryResult:
    serials: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    error: str | None = None


def _put_latest(target: queue.Queue, item: object) -> None:
    """Put without blocking, discarding the oldest queued item if necessary."""
    while True:
        try:
            target.put_nowait(item)
            return
        except queue.Full:
            try:
                target.get_nowait()
            except queue.Empty:
                continue


class BoundedTextSink:
    """Non-blocking Loguru sink suitable for the Tk polling loop."""

    def __init__(self, target: queue.Queue[str]) -> None:
        self._target = target

    def write(self, message: object) -> None:
        _put_latest(self._target, str(message))


def _friendly_device_label(serial: str) -> str:
    host, separator, port = serial.rpartition(":")
    if separator and host in {"127.0.0.1", "localhost"} and port.startswith("215"):
        return f"MEmu · {serial}"
    return f"Android · {serial}"


def discover_adb_serials() -> tuple[str, ...]:
    """Discover ADB devices with a finite socket timeout, outside the Tk thread."""
    client = adbutils.AdbClient(socket_timeout=5.0)
    return tuple(sorted(device.serial for device in client.device_list()))


def run_device_discovery(results: queue.Queue[DeviceDiscoveryResult]) -> None:
    try:
        serials = discover_adb_serials()
        result = DeviceDiscoveryResult(
            serials=serials,
            labels=tuple(_friendly_device_label(serial) for serial in serials),
        )
    except Exception as exc:
        result = DeviceDiscoveryResult(error=repr(exc))
    _put_latest(results, result)


def run_observer_worker(
    serial: str,
    cancellation: CancellationToken,
    events: EventBus,
    *,
    runtime_factory: Callable[[str, CancellationToken, EventBus], BotRuntime]
    | None = None,
) -> None:
    """Assemble one observation session with bounded external-app recovery."""
    try:
        if runtime_factory is None:
            session = DeviceSession(
                serial,
                timeout_seconds=ADB_SOCKET_TIMEOUT_SECONDS,
            )
            source = ADBCaptureSource(session)
            capture = CaptureManager(
                source,
                device_serial=session.serial,
                connection_generation=lambda: session.connection_generation,
            )
            runtime = BotRuntime(
                capture=capture,
                perception=LegacyVisionAdapter(),
                events=events,
                lifecycle=Lifecycle(),
                cancellation=cancellation,
                settings=RuntimeSettings(0.15),
                recorder=SessionRecorder(),
                recovery=RewardedAdAppSupervisor(session),
            )
        else:
            runtime = runtime_factory(serial, cancellation, events)
    except Exception as exc:
        events.publish(
            RuntimeEvent(
                EventKind.ERROR,
                time.monotonic(),
                {"phase": "gui-setup", "error": repr(exc)},
            )
        )
        return

    logger.warning(
        "GUI sem ações de gameplay; recuperação externa de anúncios está ativa."
    )
    try:
        runtime.run()
    except Exception:
        # BotRuntime owns operational error publication once run() begins.
        return


class DraftShowdownGUI(ctk.CTk):
    """Tk adapter for one explicitly selected observation runtime session."""

    def __init__(self) -> None:
        super().__init__()

        self.title("Draft Showdown — Observação segura")
        self.geometry("980x680")
        self.minsize(860, 560)

        self._closing = False
        self._close_finalized = False
        self._close_deadline: float | None = None
        self._clock = time.monotonic
        self.is_running = False
        self._available_serials: tuple[str, ...] = ()
        self._serial_by_label: dict[str, str] = {}
        self._runtime_events: EventBus | None = None
        self._cancellation: CancellationToken | None = None
        self._thread_factory = threading.Thread
        self._bot_thread: threading.Thread | None = None
        self._discovery_thread: threading.Thread | None = None
        self._discovery_results: queue.Queue[DeviceDiscoveryResult] = queue.Queue(
            maxsize=1
        )
        self._log_queue: queue.Queue[str] = queue.Queue(maxsize=500)
        self._log_line_count = 0
        self._log_sink_id: int | None = None
        self._last_lifecycle_key: tuple[float, str] | None = None
        self._last_lifecycle_status: str | None = None
        self._last_error_text: str | None = None
        self._reported_dropped_events = 0
        self._dataset_saved_count = 0
        self._dataset_session_directory = "-"
        self._session_started_at: float | None = None
        self._observations_total = 0
        self._unknown_total = 0
        self._screen_transitions = 0
        self._current_screen: str | None = None
        self._current_screen_since: float | None = None

        self._build_ui()
        self._setup_logging()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(EVENT_POLL_MS, self._process_runtime_events)
        self.after(LOG_POLL_MS, self._process_log_queue)
        self.after(DISCOVERY_POLL_MS, self._process_discovery_results)
        self.refresh_devices()

    def _build_ui(self) -> None:
        self.header_frame = ctk.CTkFrame(self, height=72, corner_radius=10)
        self.header_frame.pack(fill="x", padx=15, pady=10)

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="DRAFT SHOWDOWN · OBSERVAÇÃO",
            font=ctk.CTkFont(size=19, weight="bold"),
        )
        self.lbl_title.pack(side="left", padx=15)

        self.status_badge = ctk.CTkLabel(
            self.header_frame,
            text="🔴 PARADO",
            fg_color="#A91B0D",
            text_color="white",
            corner_radius=8,
            width=118,
            height=30,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.status_badge.pack(side="left", padx=8)

        self.btn_start = ctk.CTkButton(
            self.header_frame,
            text="▶ Iniciar observação",
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            width=150,
            state="disabled",
            command=self.start_observation,
        )
        self.btn_start.pack(side="left", padx=5)

        self.btn_pause = ctk.CTkButton(
            self.header_frame,
            text="Pausa indisponível",
            width=125,
            state="disabled",
        )
        self.btn_pause.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(
            self.header_frame,
            text="■ Parar observação",
            fg_color="#C62828",
            hover_color="#B71C1C",
            width=135,
            state="disabled",
            command=self.stop_bot,
        )
        self.btn_stop.pack(side="left", padx=5)

        device_frame = ctk.CTkFrame(self, corner_radius=10)
        device_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkLabel(device_frame, text="Dispositivo ADB explícito:").pack(
            side="left", padx=(15, 5), pady=10
        )
        self.device_option = ctk.CTkOptionMenu(
            device_frame,
            values=[DEVICE_SELECTION_PLACEHOLDER],
            width=240,
            command=self._on_device_selected,
        )
        self.device_option.pack(side="left", padx=5, pady=10)

        self.btn_refresh = ctk.CTkButton(
            device_frame,
            text="Atualizar lista",
            width=110,
            command=self.refresh_devices,
        )
        self.btn_refresh.pack(side="left", padx=8, pady=10)

        ctk.CTkLabel(
            device_frame,
            text="Sem toques de gameplay; anúncios externos usam Voltar/reabrir jogo.",
            text_color="#A9B7C6",
        ).pack(side="right", padx=15, pady=10)

        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.tab_observation = self.tabview.add("Observação")
        self.tab_future = self.tabview.add("Recursos")

        self._build_observation_tab()
        self._build_future_tab()

    def _build_observation_tab(self) -> None:
        state_frame = ctk.CTkFrame(self.tab_observation)
        state_frame.pack(fill="x", padx=8, pady=8)
        self.lbl_current_state = ctk.CTkLabel(
            state_frame,
            text="Tela: UNKNOWN | Confiança: 0% | Elemento: - | Frame: -",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.lbl_current_state.pack(anchor="w", padx=15, pady=10)
        self.lbl_context_state = ctk.CTkLabel(
            state_frame,
            text="Contexto: aguardando observações",
            text_color="#FFE082",
        )
        self.lbl_context_state.pack(anchor="w", padx=15, pady=(0, 6))
        self.lbl_session_state = ctk.CTkLabel(
            state_frame,
            text="Sessão: - | Observações: 0 | Transições: 0 | UNKNOWN: 0",
            text_color="#D6DEE6",
        )
        self.lbl_session_state.pack(anchor="w", padx=15, pady=(0, 6))
        self.lbl_capture_state = ctk.CTkLabel(
            state_frame,
            text="Captura: aguardando | Válidos: 0 | Pretos descartados: 0",
            text_color="#A9B7C6",
        )
        self.lbl_capture_state.pack(anchor="w", padx=15, pady=(0, 6))
        self.lbl_dataset_state = ctk.CTkLabel(
            state_frame,
            text="Dataset: 0 imagens | Pasta: será criada na primeira captura útil",
            text_color="#A9B7C6",
        )
        self.lbl_dataset_state.pack(anchor="w", padx=15, pady=(0, 10))

        ctk.CTkLabel(
            self.tab_observation,
            text="Eventos do runtime (somente leitura)",
        ).pack(anchor="w", padx=10, pady=(4, 0))
        self.log_textbox = ctk.CTkTextbox(
            self.tab_observation,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_textbox.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_future_tab(self) -> None:
        panel = ctk.CTkFrame(self.tab_future)
        panel.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(
            panel,
            text="RECURSOS DA CONTA",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#81C784",
        ).pack(anchor="w", padx=18, pady=(18, 8))
        self.lbl_resources_primary = ctk.CTkLabel(
            panel,
            text="Energia: -/- | Gemas: - | Moedas: - | Maestria: - M",
            font=ctk.CTkFont(size=15, weight="bold"),
            justify="left",
            wraplength=760,
        )
        self.lbl_resources_primary.pack(anchor="w", padx=18, pady=8)
        self.lbl_resources_progress = ctk.CTkLabel(
            panel,
            text="Troféus: - | Nível: - | Liga: - | Posição: - | Pontos: -",
            justify="left",
            wraplength=900,
        )
        self.lbl_resources_progress.pack(anchor="w", padx=18, pady=8)
        self.lbl_resources_collection = ctk.CTkLabel(
            panel,
            text="Coleção: aguardando visita à tela | Unidades visíveis: -",
            justify="left",
            wraplength=900,
        )
        self.lbl_resources_collection.pack(anchor="w", padx=18, pady=8)
        self.lbl_resources_status = ctk.CTkLabel(
            panel,
            text="OCR: aguardando primeira leitura confiável",
            text_color="#A9B7C6",
        )
        self.lbl_resources_status.pack(anchor="w", padx=18, pady=(8, 18))
        ctk.CTkLabel(
            panel,
            text=(
                "Os valores são lidos de regiões específicas da imagem e o último valor "
                "confiável é preservado durante batalha e transições. Automação de gastos, "
                "impulsos e upgrades continua bloqueada até haver política e pós-condição."
            ),
            justify="left",
            wraplength=900,
            text_color="#FFE082",
        ).pack(anchor="w", padx=18, pady=8)

    def _setup_logging(self) -> None:
        sink = BoundedTextSink(self._log_queue)
        self._log_sink_id = logger.add(
            sink.write,
            format="{time:HH:mm:ss} | {level: <7} | {message}\n",
            level="INFO",
        )

    def refresh_devices(self) -> None:
        if self._closing:
            return
        if self._discovery_thread is not None and self._discovery_thread.is_alive():
            return
        if self._bot_thread is not None:
            return

        self._available_serials = ()
        self._serial_by_label = {}
        self.device_option.configure(values=["Buscando dispositivos..."])
        self.device_option.set("Buscando dispositivos...")
        self.btn_start.configure(state="disabled")
        self.btn_refresh.configure(state="disabled")
        try:
            worker = self._thread_factory(
                target=run_device_discovery,
                args=(self._discovery_results,),
                daemon=True,
                name="draft-showdown-adb-discovery",
            )
            self._discovery_thread = worker
            worker.start()
        except Exception as exc:
            self._discovery_thread = None
            self._available_serials = ()
            self.device_option.configure(values=["Falha na busca ADB"])
            self.device_option.set("Falha na busca ADB")
            self.btn_start.configure(state="disabled")
            self.btn_refresh.configure(state="normal")
            logger.error("Não foi possível iniciar a busca ADB: {!r}", exc)

    def _process_discovery_results(self) -> None:
        if self._closing:
            return
        try:
            result = self._discovery_results.get_nowait()
        except queue.Empty:
            result = None

        if result is not None:
            self._discovery_thread = None
            if result.error is not None:
                logger.error("Falha ao buscar dispositivos ADB: {}", result.error)
                values = ["ADB indisponível"]
                self._available_serials = ()
            elif result.serials:
                self._available_serials = result.serials
                labels = result.labels if len(result.labels) == len(result.serials) else result.serials
                self._serial_by_label = dict(zip(labels, result.serials, strict=True))
                values = [DEVICE_SELECTION_PLACEHOLDER, *labels]
            else:
                values = ["Nenhum dispositivo ADB"]
                self._available_serials = ()
            self.device_option.configure(values=values)
            if len(result.serials) == 1:
                self.device_option.set(values[1])
                logger.info("Único dispositivo ADB selecionado automaticamente: {}", values[1])
            elif result.serials:
                self.device_option.set(DEVICE_SELECTION_PLACEHOLDER)
            else:
                self.device_option.set(values[0])
            self.btn_refresh.configure(state="normal")
            self._update_controls()

        self.after(DISCOVERY_POLL_MS, self._process_discovery_results)

    def _on_device_selected(self, _selected: str) -> None:
        self._update_controls()

    def start_observation(self) -> None:
        if self._closing or self.is_running or self._bot_thread is not None:
            return

        selected_device = self.device_option.get().strip()
        serial = self._serial_by_label.get(selected_device, selected_device)
        if serial not in self._available_serials:
            logger.error("Selecione explicitamente um dispositivo ADB disponível.")
            return

        cancellation = CancellationToken()
        events = EventBus(capacity=512)
        self._cancellation = cancellation
        self._runtime_events = events
        self._last_lifecycle_key = None
        self._last_lifecycle_status = None
        self._last_error_text = None
        self._reported_dropped_events = 0
        self._dataset_saved_count = 0
        self._dataset_session_directory = "-"
        self._session_started_at = self._clock()
        self._observations_total = 0
        self._unknown_total = 0
        self._screen_transitions = 0
        self._current_screen = None
        self._current_screen_since = None
        self.is_running = True

        self.status_badge.configure(text="🟠 INICIANDO", fg_color="#E65100")
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_refresh.configure(state="disabled")

        try:
            worker = self._thread_factory(
                target=run_observer_worker,
                args=(serial, cancellation, events),
                daemon=True,
                name="draft-showdown-observer",
            )
            self._bot_thread = worker
            worker.start()
        except Exception as exc:
            cancellation.cancel()
            self._bot_thread = None
            self._cancellation = None
            self._runtime_events = None
            self.is_running = False
            self.status_badge.configure(text="🔴 FALHA", fg_color="#A91B0D")
            self.btn_stop.configure(state="disabled")
            logger.error("Não foi possível iniciar o worker: {!r}", exc)
            self._update_controls()

    def stop_bot(self) -> None:
        if not self.is_running or self._cancellation is None:
            return
        self._cancellation.cancel()
        self.status_badge.configure(text="🟠 PARANDO", fg_color="#E65100")
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        logger.info("Parada cooperativa solicitada.")

    def _process_runtime_events(self) -> None:
        if self._closing:
            return

        events = self._runtime_events
        if events is not None:
            self._consume_runtime_events(events)

        self._reap_worker(events)
        self.after(EVENT_POLL_MS, self._process_runtime_events)

    def _consume_runtime_events(self, events: EventBus) -> None:
        for event in events.drain():
            self._apply_runtime_event(event)

        latest_lifecycle = events.latest_lifecycle
        if latest_lifecycle is not None:
            self._apply_runtime_event(latest_lifecycle)
        latest_error = events.latest_error
        if latest_error is not None:
            self._apply_runtime_event(latest_error)

        dropped = events.dropped_count
        if dropped > self._reported_dropped_events:
            logger.warning(
                "Fila de eventos cheia: {} evento(s) de dados descartado(s).",
                dropped - self._reported_dropped_events,
            )
            self._reported_dropped_events = dropped

    def _apply_runtime_event(self, event: RuntimeEvent) -> None:
        observation = format_runtime_event(event)
        if observation is not None:
            self.lbl_current_state.configure(text=observation)
            self._update_context_details(event)
            self._update_observation_metrics(event)
            self._update_resource_details(event)
            return

        if event.kind is EventKind.FRAME:
            self.lbl_capture_state.configure(
                text=(
                    f"Captura: {event.payload.get('capture_strategy', '-')} | "
                    f"Válidos: {event.payload.get('valid_frames', 0)} | "
                    f"Pretos descartados: {event.payload.get('blank_frames', 0)} | "
                    f"Recuperações: {event.payload.get('capture_recoveries', 0)} | "
                    f"Resets ADB: {event.payload.get('capture_connection_resets', 0)}"
                ),
                text_color="#A9B7C6",
            )
            return

        if event.kind is EventKind.CAPTURE:
            degraded = event.payload.get("status") == "degraded"
            self.lbl_capture_state.configure(
                text=(
                    f"Captura: {'instável, tentando novamente' if degraded else 'recuperada'} | "
                    f"Válidos: {event.payload.get('valid_frames', 0)} | "
                    f"Pretos descartados: {event.payload.get('blank_frames', 0)} | "
                    f"Ciclos seguidos: {event.payload.get('consecutive_capture_failures', 0)} | "
                    f"Resets ADB: {event.payload.get('capture_connection_resets', 0)}"
                ),
                text_color="#FFB74D" if degraded else "#81C784",
            )
            return

        if event.kind is EventKind.RECOVERY:
            status = str(event.payload.get("status", "-")).upper()
            method = event.payload.get("method", "-")
            package = event.payload.get("external_package", "-")
            logger.info(
                "Recuperação externa: {} via {} (origem: {})",
                status,
                method,
                package,
            )
            self.lbl_context_state.configure(
                text=f"Recuperação de anúncio: {status} via {method} | {package}"
            )
            return

        if event.kind is EventKind.DATASET:
            if event.payload.get("status") == "saved":
                self._dataset_saved_count = int(event.payload.get("saved_count", 0))
                self._dataset_session_directory = str(event.payload.get("session_directory") or "-")
                session_name = self._dataset_session_directory.replace("\\", "/").rstrip("/").split("/")[-1]
                self.lbl_dataset_state.configure(
                    text=(
                        f"Dataset: {self._dataset_saved_count} imagens | "
                        f"Último motivo: {event.payload.get('reason', '-')} | Sessão: {session_name}"
                    )
                )
                logger.info(
                    "Dataset: frame útil {} salvo ({})",
                    self._dataset_saved_count,
                    event.payload.get("reason", "seleção automática"),
                )
            elif event.payload.get("error"):
                logger.warning("Gravação de dataset desabilitada: {}", event.payload["error"])
            return

        lifecycle = present_lifecycle(event)
        if lifecycle is not None:
            status = str(event.payload.get("status"))
            key = (event.emitted_at_monotonic, status)
            if key == self._last_lifecycle_key:
                return
            self._last_lifecycle_key = key
            self._last_lifecycle_status = status
            self.status_badge.configure(text=lifecycle.label, fg_color=lifecycle.color)
            if lifecycle.terminal:
                self.is_running = False
                self.btn_stop.configure(state="disabled")
                self._update_controls()
            return

        error = format_runtime_error(event)
        if error is None:
            return
        raw_error = str(event.payload.get("error") or "erro desconhecido")
        if raw_error == self._last_error_text:
            return
        self._last_error_text = raw_error
        logger.error("Runtime de observação: {}", error)
        self.is_running = False
        self.status_badge.configure(text="🔴 FALHA", fg_color="#A91B0D")
        self.btn_stop.configure(state="disabled")
        self._update_controls()

    def _update_observation_metrics(self, event: RuntimeEvent) -> None:
        now = self._clock()
        screen = str(event.payload.get("screen") or "UNKNOWN")
        self._observations_total += 1
        if screen == "UNKNOWN":
            self._unknown_total += 1
        if self._current_screen is None:
            self._current_screen = screen
            self._current_screen_since = now
        elif screen != self._current_screen:
            self._screen_transitions += 1
            self._current_screen = screen
            self._current_screen_since = now
        started = self._session_started_at if self._session_started_at is not None else now
        stable_since = self._current_screen_since if self._current_screen_since is not None else now
        elapsed = max(0, round(now - started))
        minutes, seconds = divmod(elapsed, 60)
        unknown_rate = self._unknown_total / self._observations_total
        self.lbl_session_state.configure(
            text=(
                f"Sessão: {minutes:02d}:{seconds:02d} | Observações: {self._observations_total} | "
                f"Transições: {self._screen_transitions} | UNKNOWN: {self._unknown_total} "
                f"({unknown_rate:.1%}) | Tela estável: {max(0.0, now - stable_since):.1f}s"
            )
        )

    def _update_resource_details(self, event: RuntimeEvent) -> None:
        resources = event.payload.get("resources")
        if not isinstance(resources, dict) and not hasattr(resources, "get"):
            return

        def value(name: str, default: object = "-") -> object:
            raw = resources.get(name, default)
            return default if raw is None else raw

        self.lbl_resources_primary.configure(
            text=(
                f"Energia: {value('energy_current')}/{value('energy_capacity')} | "
                f"Gemas: {value('gems')} | Moedas: {value('coins')} | "
                f"Maestria: {value('mastery_currency')} M"
            )
        )
        rank = value("league_rank")
        rank_text = f"#{rank}" if rank != "-" else "-"
        self.lbl_resources_progress.configure(
            text=(
                f"Troféus: {value('trophies')} | Nível: {value('player_level')} | "
                f"Liga: {value('league')} | Posição: {rank_text} | "
                f"Pontos: {value('league_points')} | Termina: {value('league_ends')}"
            )
        )
        units = resources.get("units", ())
        unit_text = ", ".join(
            (
                f"{unit.get('name', '?')} Nv.{unit.get('level', '?')}"
                + (f" / M.{unit.get('mastery')}" if unit.get("mastery") is not None else "")
            )
            for unit in units
            if hasattr(unit, "get")
        ) or "-"
        self.lbl_resources_collection.configure(
            text=(
                f"Coleção: {value('collection_unlocked')}/{value('collection_total')} | "
                f"Unidades visíveis: {unit_text}"
            )
        )
        confidence = resources.get("resource_confidence")
        confidence_text = f" | confiança mínima {float(confidence):.0%}" if confidence is not None else ""
        status = str(event.payload.get("resource_ocr_status") or "cached")
        self.lbl_resources_status.configure(
            text=f"OCR: {'leitura nova' if status == 'fresh' else 'último valor confiável'}{confidence_text}"
        )

    def _update_context_details(self, event: RuntimeEvent) -> None:
        context = event.payload.get("context")
        if context == "daily_offers":
            free_ads = int(event.payload.get("free_ad_offers_visible", 0))
            refresh_ad = "sim" if event.payload.get("daily_refresh_ad_visible") else "não visível"
            reward_status = (
                "DISPONÍVEL AGORA"
                if event.payload.get("ad_reward_available_now")
                else "em recarga/sem botão disponível"
            )
            countdown = (
                "visível; leitura numérica pendente"
                if event.payload.get("next_refresh_countdown_visible")
                else "fora do enquadramento"
            )
            text = (
                f"Recompensa por anúncio: {reward_status} ({free_ads} visível(is)) | "
                f"Atualização por anúncio: {refresh_ad} | Próxima renovação: {countdown}"
            )
        elif context == "shop":
            text = "Loja: ofertas pagas e por anúncio; role até Ofertas diárias para detalhamento"
        elif context == "rewarded_ad":
            safe = bool(event.payload.get("safe_to_close"))
            text = (
                "Anúncio recompensado: RECOMPENSA CONFIRMADA | Fechamento seguro: SIM"
                if safe
                else "Anúncio recompensado: aguardando timer/barra | Fechamento seguro: NÃO"
            )
        elif context == "league":
            text = "Liga: BRONZE | Troféus/ranking visíveis; leitura numérica ainda pendente"
        elif context == "ranked":
            text = "Modo ranqueado: BLOQUEADO"
        elif context == "profile":
            text = "Perfil: estatísticas do jogador visíveis"
        else:
            text = f"Contexto: {event.payload.get('screen', 'UNKNOWN')}"
        self.lbl_context_state.configure(text=text)

    def _reap_worker(self, events: EventBus | None) -> None:
        worker = self._bot_thread
        if worker is None or worker.is_alive():
            return
        worker.join(timeout=0)
        if events is not None:
            self._consume_runtime_events(events)

        terminal = self._last_lifecycle_status in {"stopped", "failed"}
        cancelled = self._cancellation is not None and self._cancellation.cancelled
        if not terminal:
            self.is_running = False
            if self._last_error_text is None:
                if cancelled:
                    self.status_badge.configure(
                        text="🔴 PARADO",
                        fg_color="#A91B0D",
                    )
                else:
                    logger.error(
                        "Worker de observação terminou sem lifecycle terminal."
                    )
                    self.status_badge.configure(
                        text="🔴 FALHA",
                        fg_color="#A91B0D",
                    )
            self.btn_stop.configure(state="disabled")

        self._bot_thread = None
        self._cancellation = None
        if self._runtime_events is events:
            self._runtime_events = None
        self._update_controls()

    def _update_controls(self) -> None:
        can_start = (
            not self._closing
            and not self.is_running
            and self._bot_thread is None
            and self._serial_by_label.get(
                self.device_option.get().strip(), self.device_option.get().strip()
            ) in self._available_serials
        )
        self.btn_start.configure(state="normal" if can_start else "disabled")
        self.btn_pause.configure(state="disabled")
        if not self.is_running:
            self.btn_stop.configure(state="disabled")
        discovering = (
            self._discovery_thread is not None and self._discovery_thread.is_alive()
        )
        self.btn_refresh.configure(
            state=(
                "disabled"
                if self._closing
                or self.is_running
                or self._bot_thread is not None
                or discovering
                else "normal"
            )
        )

    def _process_log_queue(self) -> None:
        if self._closing:
            return
        inserted = False
        for _ in range(200):
            try:
                message = self._log_queue.get_nowait()
            except queue.Empty:
                break
            if not message:
                continue
            if not message.endswith("\n"):
                message += "\n"
            self.log_textbox.insert("end", message)
            self._log_line_count += message.count("\n")
            inserted = True

        excess_lines = self._log_line_count - MAX_LOG_LINES
        if excess_lines > 0:
            self.log_textbox.delete("1.0", f"{excess_lines + 1}.0")
            self._log_line_count -= excess_lines
        if inserted:
            self.log_textbox.see("end")
        self.after(LOG_POLL_MS, self._process_log_queue)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.status_badge.configure(text="🟠 ENCERRANDO", fg_color="#E65100")
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="disabled")
        self.btn_stop.configure(state="disabled")
        self.btn_refresh.configure(state="disabled")
        if self._cancellation is not None:
            self._cancellation.cancel()
        self._close_deadline = self._clock() + CLOSE_TIMEOUT_SECONDS
        self._poll_close()

    def _poll_close(self) -> None:
        if self._close_finalized:
            return

        worker = self._bot_thread
        if worker is None:
            self._finalize_close()
            return

        if not worker.is_alive():
            self._reap_worker(self._runtime_events)
            self._finalize_close()
            return

        deadline = self._close_deadline
        if deadline is not None and self._clock() >= deadline:
            if self._runtime_events is not None:
                self._consume_runtime_events(self._runtime_events)
            logger.warning(
                "Worker daemon não encerrou em {:.1f}s; fechando a GUI com fallback.",
                CLOSE_TIMEOUT_SECONDS,
            )
            self._finalize_close()
            return

        self.after(CLOSE_POLL_MS, self._poll_close)

    def _finalize_close(self) -> None:
        if self._close_finalized:
            return
        self._close_finalized = True
        try:
            if self._log_sink_id is not None:
                logger.remove(self._log_sink_id)
        except Exception:
            pass
        finally:
            self._log_sink_id = None
            self.destroy()


def main() -> None:
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    app = DraftShowdownGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
