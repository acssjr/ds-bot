from loguru import logger
from typing import List

from src.state.game_state import CardChoice

class DraftEvaluator:
    """Aplica a matriz de pontuação e utilidade para selecionar a melhor carta oferecida."""

    def evaluate_choices(self, choices: List[CardChoice]) -> int:
        """
        Retorna o índice do slot (0, 1 ou 2) escolhido.
        No MVP 1, padrão cego: seleciona o Slot 0.
        """
        if not choices:
            return 0

        # Para MVP 1 (Draft Cego / Inicial)
        logger.debug("DraftEvaluator MVP 1: Selecionando Slot 0 por padrão")
        return 0
