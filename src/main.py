import time
from loguru import logger

from src.utils.logging_config import setup_logger
from src.utils.watchdog import Watchdog
from src.capture.adb_capture import ADBCapture
from src.vision.pipeline import VisionPipeline
from src.state.state_manager import StateManager
from src.state.game_state import ScreenState
from src.strategy.draft_evaluator import DraftEvaluator
from src.actions.action_planner import ActionPlanner
from src.controllers.adb_controller import ADBController

def main() -> None:
    logger = setup_logger("INFO")
    logger.info("==================================================")
    logger.info("Iniciando Bot Autônomo - Draft Showdown (Visão + Ads)")
    logger.info("==================================================")

    capture_stream = ADBCapture()
    if not capture_stream.start():
        logger.error("Falha ao inicializar o leitor de tela ADB. Verifique a conexão com o emulador MEmu.")
        return

    vision_pipeline = VisionPipeline(templates_dir="assets/templates")
    state_manager = StateManager(persistence_frames=2)
    draft_evaluator = DraftEvaluator()
    action_planner = ActionPlanner()
    controller = ADBController()
    watchdog = Watchdog(timeout_seconds=35)

    watch_ads_policy = True  # Politica de assistir anúncios ativada

    logger.info("Loop de automação em execução. Pressione Ctrl+C para encerrar.")

    try:
        while True:
            # 1. Captura do Frame Atual
            frame = capture_stream.get_latest_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            h, w = frame.shape[:2]
            controller.update_screen_size(w, h)

            # 2. Processamento de Visão Computacional
            perception_data = vision_pipeline.analyze(frame)

            # 3. Atualização da FSM
            current_state = state_manager.update(perception_data)
            watchdog.feed(current_state.screen)

            # 4. Verificação de Saúde via Watchdog
            if watchdog.is_stuck():
                logger.warning("Travamento detectado pelo Watchdog! Acionando protocolo de recuperação do app...")
                controller.recover_app_state()
                state_manager.reset()
                watchdog.reset()
                continue

            # 5. Tomada de Decisão Baseada nos 13 Estados Mapeados
            chosen_action = None
            screen = current_state.screen
            sub = current_state.sub_element

            if screen == ScreenState.HOME:
                has_reiv = (sub == "reiv_home_btn")
                chosen_action = action_planner.plan_start_match(has_home_reiv=has_reiv)

            elif screen == ScreenState.DRAFT_SCREEN:
                best_slot = draft_evaluator.evaluate_choices(current_state.available_choices)
                chosen_action = action_planner.plan_card_selection(slot_index=best_slot)

            elif screen == ScreenState.POSITION_UNITS:
                chosen_action = action_planner.plan_unit_positioning()

            elif screen == ScreenState.VICTORY_SUMMARY:
                chosen_action = action_planner.plan_handle_victory_summary(sub_element=sub, watch_ads=watch_ads_policy)

            elif screen == ScreenState.DOUBLE_BITS:
                chosen_action = action_planner.plan_handle_double_bits(watch_ads=watch_ads_policy)

            elif screen == ScreenState.MASTERY_BOOST:
                chosen_action = action_planner.plan_handle_mastery_boost()

            elif screen == ScreenState.BIT_PACK_OPENING:
                chosen_action = action_planner.plan_skip_bit_pack()

            elif screen == ScreenState.NEW_UNIT_UNLOCKED:
                chosen_action = action_planner.plan_unlock_new_unit()

            elif screen == ScreenState.WATCHING_AD:
                chosen_action = action_planner.plan_close_ad(sub_element=sub)

            elif screen == ScreenState.COLLECTION_MENU:
                chosen_action = action_planner.plan_switch_to_battle_tab()

            elif screen == ScreenState.WAIT_MATCHMAKING or screen == ScreenState.COMBAT:
                logger.debug(f"Estado passivo '{screen.value}'... Monitorando tela.")
                time.sleep(0.5)

            # 6. Execução da Ação
            if chosen_action:
                logger.info(f"[{screen.value}] Executando Ação: {chosen_action.metadata}")
                controller.execute(chosen_action)
                time.sleep(chosen_action.post_delay_ms / 1000.0)

            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Encerramento solicitado pelo usuário.")
    except Exception as e:
        logger.exception(f"Exceção não tratada no loop principal: {e}")
    finally:
        capture_stream.stop()
        logger.info("Bot finalizado com sucesso.")

if __name__ == "__main__":
    main()
