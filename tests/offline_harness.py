import os
import cv2
import numpy as np
from loguru import logger
import pytest

from src.state.game_state import ScreenState, GameState
from src.utils.coordinates import CoordinateConverter
from src.vision.pipeline import VisionPipeline
from src.state.state_manager import StateManager
from src.actions.action_planner import ActionPlanner

def test_coordinate_conversion():
    w, h = 1280, 720
    px, py = 640, 360
    nx, ny = CoordinateConverter.normalize(px, py, w, h)
    assert nx == pytest.approx(640 / 1279)
    assert ny == pytest.approx(360 / 719)

    denorm_x, denorm_y = CoordinateConverter.denormalize(nx, ny, w, h)
    assert denorm_x == px
    assert denorm_y == py

def test_fsm_persistence():
    manager = StateManager(persistence_frames=2)
    data1 = {"screen": ScreenState.HOME, "confidence": 0.9, "sub_element": "batalha_btn"}
    data2 = {"screen": ScreenState.HOME, "confidence": 0.9, "sub_element": "batalha_btn"}

    state = manager.update(data1)
    assert state.screen == ScreenState.UNKNOWN

    state = manager.update(data2)
    assert state.screen == ScreenState.HOME
    assert state.sub_element == "batalha_btn"

def test_vision_pipeline_classification():
    pipeline = VisionPipeline(templates_dir="assets/templates")
    dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    perception = pipeline.analyze(dummy_frame)

    assert "screen" in perception
    assert "confidence" in perception
    assert "sub_element" in perception

def test_action_planner_ads_and_rewards():
    planner = ActionPlanner()
    
    # Teste de vitória com anúncio disponível
    act_ad = planner.plan_handle_victory_summary(sub_element="reiv_ad_btn", watch_ads=True)
    assert "Assistir Anúncio" in act_ad.metadata

    # Teste de vitória com timer de anúncio ativo (anúncio indisponível)
    act_timer = planner.plan_handle_victory_summary(sub_element="timer_ad_btn", watch_ads=True)
    assert "Continuar" in act_timer.metadata

    # Teste de navegação da Coleção para Batalha
    act_collection = planner.plan_switch_to_battle_tab()
    assert "Coleção para a aba Batalha" in act_collection.metadata

if __name__ == "__main__":
    logger.info("Executando Testes Unitários e Test Harness Offline...")
    test_coordinate_conversion()
    test_fsm_persistence()
    test_vision_pipeline_classification()
    test_action_planner_ads_and_rewards()
    logger.info("Todos os testes unitários passaram com sucesso!")
