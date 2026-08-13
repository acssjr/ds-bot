import time
from loguru import logger
from typing import Optional

class Watchdog:
    """Monitor de saúde da FSM e recuperação de travamentos em tela estática."""

    def __init__(self, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds
        self.last_state = None
        self.last_change_time = time.time()

    def feed(self, current_state) -> None:
        """Alimenta o Watchdog com o estado atual detectado."""
        if current_state != self.last_state:
            self.last_state = current_state
            self.last_change_time = time.time()

    def is_stuck(self) -> bool:
        """Retorna True se o sistema permanecer no mesmo estado além do tempo limite."""
        elapsed = time.time() - self.last_change_time
        stuck = elapsed > self.timeout_seconds
        if stuck:
            logger.warning(f"Watchdog: Travamento detectado no estado '{self.last_state}' por {elapsed:.1f}s")
        return stuck

    def reset(self) -> None:
        self.last_change_time = time.time()
