import time
from loguru import logger
from typing import Dict, Any

from src.state.game_state import GameState, ScreenState

class StateManager:
    """Gerencia a Máquina de Estados Finitos (FSM) do jogo e garante estabilidade por persistência."""

    def __init__(self, persistence_frames: int = 2):
        self.current_game_state = GameState(timestamp=time.time())
        self.persistence_frames = persistence_frames
        self.pending_state = ScreenState.UNKNOWN
        self.pending_count = 0

    def update(self, perception_data: Dict[str, Any]) -> GameState:
        """
        Atualiza o GameState com os dados de percepção visual. Exige 2 frames seguidos da mesma tela para transicionar.
        """
        detected_screen = perception_data.get("screen", ScreenState.UNKNOWN)
        confidence = perception_data.get("confidence", 0.0)
        sub_element = perception_data.get("sub_element", None)

        if detected_screen != self.current_game_state.screen:
            if detected_screen == self.pending_state:
                self.pending_count += 1
                if self.pending_count >= self.persistence_frames:
                    logger.info(f"FSM: Transição de tela confirmada '{self.current_game_state.screen}' -> '{detected_screen}' (sub: {sub_element})")
                    self.current_game_state.screen = detected_screen
                    self.pending_count = 0
            else:
                self.pending_state = detected_screen
                self.pending_count = 1
        else:
            self.pending_count = 0

        self.current_game_state.confidence = confidence
        self.current_game_state.sub_element = sub_element
        self.current_game_state.timestamp = time.time()
        if "available_choices" in perception_data:
            self.current_game_state.available_choices = perception_data["available_choices"]

        return self.current_game_state

    def reset(self) -> None:
        """Reseta o estado da FSM para UNKNOWN em protocolos de recuperação."""
        logger.warning("FSM: Resetando estado para UNKNOWN")
        self.current_game_state = GameState(timestamp=time.time())
        self.pending_state = ScreenState.UNKNOWN
        self.pending_count = 0
