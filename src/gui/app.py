import sys
import time
import threading
import queue
import adbutils
import customtkinter as ctk
from loguru import logger
from typing import Optional

from src.utils.watchdog import Watchdog
from src.capture.adb_capture import ADBCapture
from src.vision.pipeline import VisionPipeline
from src.state.state_manager import StateManager
from src.state.game_state import ScreenState, SessionStats
from src.strategy.draft_evaluator import DraftEvaluator
from src.actions.action_planner import ActionPlanner
from src.controllers.adb_controller import ADBController

# Configuração de Aparência do CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TextHandler:
    """Redireciona os logs do Loguru para a janela de texto da GUI."""
    def __init__(self, log_queue: queue.Queue):
        self.log_queue = log_queue

    def write(self, message):
        self.log_queue.put(message)

    def flush(self):
        pass

class DraftShowdownGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Draft Showdown Bot - Painel de Controle (Inspirado no MyBot.run)")
        self.geometry("980x680")
        self.minsize(900, 600)

        # Estado da Automação
        self.is_running = False
        self.is_paused = False
        self.bot_thread: Optional[threading.Thread] = None
        self.stats = SessionStats()
        self.log_queue = queue.Queue()

        # Opções de Configuração
        self.cfg_watch_ads = ctk.BooleanVar(value=True)
        self.cfg_double_bits = ctk.BooleanVar(value=True)
        self.cfg_claim_home = ctk.BooleanVar(value=True)
        self.cfg_mastery_boost = ctk.BooleanVar(value=True)
        self.cfg_draft_strategy = ctk.StringVar(value="Matriz de Utilidade")

        self._build_ui()
        self._setup_logging()
        self._refresh_device_list()

        # Loop de atualização da GUI
        self.after(200, self._process_log_queue)
        self.after(1000, self._update_stats_ui)

    def _build_ui(self):
        # Frame de Cabeçalho / Controle Superior
        self.header_frame = ctk.CTkFrame(self, height=70, corner_radius=10)
        self.header_frame.pack(fill="x", padx=15, pady=10)

        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="⚔️ DRAFT SHOWDOWN BOT",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        self.lbl_title.pack(side="left", padx=15)

        self.status_badge = ctk.CTkLabel(
            self.header_frame,
            text="🔴 PARADO",
            fg_color="#A91B0D",
            text_color="white",
            corner_radius=8,
            width=100,
            height=30,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self.status_badge.pack(side="left", padx=10)

        # Botões de Ação Principais
        self.btn_start = ctk.CTkButton(
            self.header_frame,
            text="▶ Iniciar Bot",
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            width=110,
            command=self.start_bot
        )
        self.btn_start.pack(side="left", padx=5)

        self.btn_pause = ctk.CTkButton(
            self.header_frame,
            text="⏸ Pausar",
            fg_color="#E65100",
            hover_color="#EF6C00",
            width=90,
            state="disabled",
            command=self.toggle_pause
        )
        self.btn_pause.pack(side="left", padx=5)

        self.btn_stop = ctk.CTkButton(
            self.header_frame,
            text="⏹ Parar",
            fg_color="#C62828",
            hover_color="#B71C1C",
            width=90,
            state="disabled",
            command=self.stop_bot
        )
        self.btn_stop.pack(side="left", padx=5)

        # Seletor de Emulador / ADB
        self.device_option = ctk.CTkOptionMenu(
            self.header_frame,
            values=["Buscando ADB..."],
            width=180
        )
        self.device_option.pack(side="right", padx=15)

        self.lbl_device = ctk.CTkLabel(self.header_frame, text="Emulador/ADB:")
        self.lbl_device.pack(side="right", padx=5)

        # Abas Principais (Navegação em Tabview)
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 10))

        self.tab_dashboard = self.tabview.add("📊 Dashboard & Status")
        self.tab_config = self.tabview.add("⚙️ Configurações & Ads")
        self.tab_strategy = self.tabview.add("🧠 Estratégia de Gameplay")

        self._build_dashboard_tab()
        self._build_config_tab()
        self._build_strategy_tab()

    def _build_dashboard_tab(self):
        # Painel Superior de Cards de Estatísticas
        self.stats_frame = ctk.CTkFrame(self.tab_dashboard, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=5)

        self.card_battles = self._create_stat_card(self.stats_frame, "Partidas", "0")
        self.card_winrate = self._create_stat_card(self.stats_frame, "Vitórias / Derrotas", "0V / 0D (0%)")
        self.card_ads = self._create_stat_card(self.stats_frame, "Anúncios Assistidos", "0")
        self.card_uptime = self._create_stat_card(self.stats_frame, "Tempo Rodando", "00:00:00")

        # Estado da Tela Atual
        self.state_info_frame = ctk.CTkFrame(self.tab_dashboard, height=40)
        self.state_info_frame.pack(fill="x", pady=5)

        self.lbl_current_state = ctk.CTkLabel(
            self.state_info_frame,
            text="Tela Detectada: UNKNOWN (Confiança: 0%)",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.lbl_current_state.pack(side="left", padx=15, pady=5)

        # Console de Logs em Tempo Real
        self.lbl_log_title = ctk.CTkLabel(self.tab_dashboard, text="Console de Logs em Tempo Real:")
        self.lbl_log_title.pack(anchor="w", padx=5, pady=(5, 0))

        self.log_textbox = ctk.CTkTextbox(self.tab_dashboard, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_textbox.pack(fill="both", expand=True, pady=5)

    def _create_stat_card(self, parent, title: str, default_val: str):
        card = ctk.CTkFrame(parent, width=210, height=70)
        card.pack(side="left", expand=True, fill="both", padx=5)

        lbl_t = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11), text_color="gray")
        lbl_t.pack(anchor="w", padx=10, pady=(5, 0))

        lbl_v = ctk.CTkLabel(card, text=default_val, font=ctk.CTkFont(size=16, weight="bold"))
        lbl_v.pack(anchor="w", padx=10, pady=(0, 5))

        return lbl_v

    def _build_config_tab(self):
        frame = ctk.CTkFrame(self.tab_config)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        lbl_sec = ctk.CTkLabel(frame, text="Automação de Anúncios e Recompensas", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_sec.pack(anchor="w", padx=15, pady=15)

        sw1 = ctk.CTkSwitch(frame, text="Assistir Anúncios de Vitória para Pacote Bônus", variable=self.cfg_watch_ads)
        sw1.pack(anchor="w", padx=20, pady=10)

        sw2 = ctk.CTkSwitch(frame, text="Assistir Anúncios para Duplicar Bits (🎬 x2 BITS)", variable=self.cfg_double_bits)
        sw2.pack(anchor="w", padx=20, pady=10)

        sw3 = ctk.CTkSwitch(frame, text="Resgatar Recompensas de Bits/Packs da Tela Inicial (Home)", variable=self.cfg_claim_home)
        sw3.pack(anchor="w", padx=20, pady=10)

        sw4 = ctk.CTkSwitch(frame, text="Avançar Impulso de Maestria Pós-Vitória", variable=self.cfg_mastery_boost)
        sw4.pack(anchor="w", padx=20, pady=10)

    def _build_strategy_tab(self):
        frame = ctk.CTkFrame(self.tab_strategy)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        lbl_sec = ctk.CTkLabel(frame, text="Modo de Seleção de Cartas (Draft)", font=ctk.CTkFont(size=16, weight="bold"))
        lbl_sec.pack(anchor="w", padx=15, pady=15)

        opt_strat = ctk.CTkOptionMenu(
            frame,
            values=["Matriz de Utilidade (Inteligente)", "Draft Cego (Slot 0)"],
            variable=self.cfg_draft_strategy,
            width=260
        )
        opt_strat.pack(anchor="w", padx=20, pady=10)

        lbl_note = ctk.CTkLabel(
            frame,
            text="Nota: A Matriz de Utilidade pontua as cartas por papéis (Tank, DPS, Utility) para montar composições equilibradas.",
            text_color="gray",
            wraplength=600,
            justify="left"
        )
        lbl_note.pack(anchor="w", padx=20, pady=10)

    def _refresh_device_list(self):
        try:
            devices = adbutils.adb.device_list()
            serials = [d.serial for d in devices] if devices else ["Nenhum dispositivo via ADB"]
            self.device_option.configure(values=serials)
            self.device_option.set(serials[0])
        except Exception:
            self.device_option.configure(values=["ADB não encontrado"])

    def _setup_logging(self):
        handler = TextHandler(self.log_queue)
        logger.add(handler.write, format="{time:HH:mm:ss} | {level: <7} | {message}\n", level="INFO")

    def _process_log_queue(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_textbox.insert("end", msg)
            self.log_textbox.see("end")
        self.after(200, self._process_log_queue)

    def _update_stats_ui(self):
        if self.is_running:
            self.card_battles.configure(text=str(self.stats.total_battles))
            self.card_winrate.configure(text=f"{self.stats.wins}V / {self.stats.losses}D ({self.stats.win_rate:.1f}%)")
            self.card_ads.configure(text=str(self.stats.ads_watched))
            self.card_uptime.configure(text=self.stats.uptime_str)
        self.after(1000, self._update_stats_ui)

    def start_bot(self):
        if self.is_running:
            return

        self.is_running = True
        self.is_paused = False
        self.stats = SessionStats()

        self.status_badge.configure(text="🟢 RODANDO", fg_color="#2E7D32")
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸ Pausar")
        self.btn_stop.configure(state="normal")

        serial = self.device_option.get()
        if serial.startswith("Nenhum") or serial.startswith("ADB"):
            serial = None

        self.bot_thread = threading.Thread(target=self._run_bot_loop, args=(serial,), daemon=True)
        self.bot_thread.start()

    def toggle_pause(self):
        if not self.is_running:
            return
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.status_badge.configure(text="🟠 PAUSADO", fg_color="#E65100")
            self.btn_pause.configure(text="▶ Retomar")
        else:
            self.status_badge.configure(text="🟢 RODANDO", fg_color="#2E7D32")
            self.btn_pause.configure(text="⏸ Pausar")

    def stop_bot(self):
        if not self.is_running:
            return

        self.is_running = False
        self.is_paused = False

        self.status_badge.configure(text="🔴 PARADO", fg_color="#A91B0D")
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸ Pausar")
        self.btn_stop.configure(state="disabled")
        logger.info("Bot interrompido pelo usuário via GUI.")

    def _run_bot_loop(self, device_serial: Optional[str]):
        logger.info(f"Iniciando Bot na thread de segundo plano (Dispositivo: {device_serial or 'Padrão'})...")

        capture_stream = ADBCapture(device_serial=device_serial)
        if not capture_stream.start():
            logger.error("Falha ao conectar no emulador. Bot parado.")
            self.stop_bot()
            return

        vision_pipeline = VisionPipeline(templates_dir="assets/templates")
        state_manager = StateManager(persistence_frames=2)
        draft_evaluator = DraftEvaluator()
        action_planner = ActionPlanner()
        controller = ADBController(device_serial=device_serial)
        watchdog = Watchdog(timeout_seconds=35)

        try:
            while self.is_running:
                if self.is_paused:
                    time.sleep(0.5)
                    continue

                frame = capture_stream.get_latest_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                h, w = frame.shape[:2]
                controller.update_screen_size(w, h)

                perception_data = vision_pipeline.analyze(frame)
                current_state = state_manager.update(perception_data)
                watchdog.feed(current_state.screen)

                # Atualiza display de tela na GUI
                screen = current_state.screen
                conf = current_state.confidence * 100.0
                sub = current_state.sub_element
                self.lbl_current_state.configure(text=f"Tela Detectada: {screen.value} ({conf:.0f}%) [sub: {sub}]")

                if watchdog.is_stuck():
                    logger.warning("Watchdog: Travamento detectado! Reiniciando app...")
                    controller.recover_app_state()
                    state_manager.reset()
                    watchdog.reset()
                    continue

                # Tomada de Decisão considerando Opções da GUI
                chosen_action = None

                if screen == ScreenState.HOME:
                    has_reiv = (sub == "reiv_home_btn") and self.cfg_claim_home.get()
                    chosen_action = action_planner.plan_start_match(has_home_reiv=has_reiv)

                elif screen == ScreenState.DRAFT_SCREEN:
                    best_slot = draft_evaluator.evaluate_choices(current_state.available_choices)
                    chosen_action = action_planner.plan_card_selection(slot_index=best_slot)

                elif screen == ScreenState.POSITION_UNITS:
                    chosen_action = action_planner.plan_unit_positioning()

                elif screen == ScreenState.VICTORY_SUMMARY:
                    chosen_action = action_planner.plan_handle_victory_summary(
                        sub_element=sub,
                        watch_ads=self.cfg_watch_ads.get()
                    )
                    if sub == "reiv_ad_btn" and self.cfg_watch_ads.get():
                        self.stats.ads_watched += 1

                elif screen == ScreenState.DOUBLE_BITS:
                    chosen_action = action_planner.plan_handle_double_bits(watch_ads=self.cfg_double_bits.get())
                    if self.cfg_double_bits.get():
                        self.stats.ads_watched += 1

                elif screen == ScreenState.MASTERY_BOOST:
                    chosen_action = action_planner.plan_handle_mastery_boost()

                elif screen == ScreenState.BIT_PACK_OPENING:
                    chosen_action = action_planner.plan_skip_bit_pack()
                    self.stats.bits_collected += 1

                elif screen == ScreenState.NEW_UNIT_UNLOCKED:
                    chosen_action = action_planner.plan_unlock_new_unit()

                elif screen == ScreenState.WATCHING_AD:
                    chosen_action = action_planner.plan_close_ad(sub_element=sub)

                elif screen == ScreenState.COLLECTION_MENU:
                    chosen_action = action_planner.plan_switch_to_battle_tab()

                elif screen in (ScreenState.WAIT_MATCHMAKING, ScreenState.COMBAT):
                    time.sleep(0.4)

                if chosen_action:
                    logger.info(f"[{screen.value}] {chosen_action.metadata}")
                    controller.execute(chosen_action)
                    time.sleep(chosen_action.post_delay_ms / 1000.0)

                time.sleep(0.1)

        except Exception as e:
            logger.exception(f"Erro na thread do bot: {e}")
        finally:
            capture_stream.stop()
            logger.info("Thread do bot finalizada.")

if __name__ == "__main__":
    app = DraftShowdownGUI()
    app.mainloop()
