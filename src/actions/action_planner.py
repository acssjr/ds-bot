from loguru import logger
from typing import Optional

from src.actions.action_model import Action, ActionType

class ActionPlanner:
    """Planeja as ações de toque e navegação normalizadas para todos os 13 estados da FSM."""

    # Posições normalizadas [x, y] no espaço [0.0, 1.0]
    POSITIONS = {
        # HOME & MENUS
        "BATTLE_BUTTON": (0.50, 0.75),       # Botão verde grande BATALHA
        "CLAIM_HOME_BUTTON": (0.50, 0.58),  # Botão verde REIV. de Bits na Home
        "BATALHA_TAB": (0.50, 0.92),        # Aba Batalha no menu inferior
        "COLECAO_TAB": (0.30, 0.92),        # Aba Coleção no menu inferior

        # DRAFT
        "DRAFT_SLOT_0": (0.22, 0.50),       # Slot 0 de carta
        "DRAFT_SLOT_1": (0.50, 0.50),       # Slot 1 de carta
        "DRAFT_SLOT_2": (0.78, 0.50),       # Slot 2 de carta
        "LOCK_IN_BUTTON": (0.85, 0.88),     # Botão Lock In na Arena

        # VICTORY SUMMARY & ADS
        "REIV_AD_BUTTON": (0.46, 0.76),     # Botão grande REIV. com ícone de filme em Victory
        "CONTINUAR_BROWN_BTN": (0.65, 0.91), # Botão Continuar em Victory
        "SEM_ADS_BTN": (0.26, 0.91),         # Botão Sem ads em Victory

        # DOUBLE BITS
        "X2_BITS_AD_BTN": (0.46, 0.72),     # Botão 🎬 x2 BITS
        "CONTINUAR_GREEN_BTN": (0.46, 0.84), # Botão CONTINUAR verde

        # MASTERY BOOST & BIT PACK & NEW UNIT
        "CONTINUAR_BOOST_BTN": (0.50, 0.84), # Botão CONTINUAR de impulso
        "TOQUE_PULAR_CENTER": (0.50, 0.50),  # Toque central para abrir Bit Pack
        "CONTINUAR_UNIT_BTN": (0.46, 0.78),  # Botão CONTINUAR de nova unidade

        # WATCHING ADS
        "CLOSE_AD_X_BTN": (0.88, 0.08),     # Ícone X de fechar anúncio no canto superior direito
        "REWARD_GRANTED_CENTER": (0.50, 0.60), # Toque para dispensar popup de recompensa concedida
    }

    def plan_start_match(self, has_home_reiv: bool = False) -> Action:
        """Na Home: se houver recompensa REIV. pendente, coleta antes de clicar em BATALHA."""
        if has_home_reiv:
            return Action(
                action_type=ActionType.TAP,
                normalized_start=self.POSITIONS["CLAIM_HOME_BUTTON"],
                post_delay_ms=800,
                metadata="Coletar Recompensa de Bits na Home"
            )
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["BATTLE_BUTTON"],
            post_delay_ms=1000,
            metadata="Iniciar Batalha (Home -> Matchmaking)"
        )

    def plan_card_selection(self, slot_index: int = 0) -> Action:
        slot_key = f"DRAFT_SLOT_{min(2, max(0, slot_index))}"
        pos = self.POSITIONS.get(slot_key, self.POSITIONS["DRAFT_SLOT_0"])
        return Action(
            action_type=ActionType.TAP,
            normalized_start=pos,
            post_delay_ms=600,
            metadata=f"Selecionar Carta Slot {slot_index}"
        )

    def plan_unit_positioning(self) -> Action:
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["LOCK_IN_BUTTON"],
            post_delay_ms=1000,
            metadata="Confirmar Posicionamento (Lock In)"
        )

    def plan_handle_victory_summary(self, sub_element: Optional[str], watch_ads: bool = True) -> Action:
        """
        Gerencia a tela de Vitória com suporte inteligente a Anúncios:
        Se o temporizador estiver ativo (ex: 'timer_ad_btn'), clica em Continuar.
        Se anúncios estiverem disponíveis e permitidos, clica no botão verde REIV. de anúncio.
        """
        if sub_element == "timer_ad_btn" or not watch_ads:
            logger.info("VictorySummary: Anúncio indisponível (timer ativo) ou desativado -> Clicando em Continuar")
            return Action(
                action_type=ActionType.TAP,
                normalized_start=self.POSITIONS["CONTINUAR_BROWN_BTN"],
                post_delay_ms=1000,
                metadata="Continuar (Bypass de Ad)"
            )
        else:
            logger.info("VictorySummary: Anúncio disponível -> Assistindo Anúncio para Bônus de Vitória")
            return Action(
                action_type=ActionType.TAP,
                normalized_start=self.POSITIONS["REIV_AD_BUTTON"],
                post_delay_ms=1500,
                metadata="Assistir Anúncio de Vitória (REIV.)"
            )

    def plan_handle_double_bits(self, watch_ads: bool = True) -> Action:
        """Duplica os bits obtidos assistindo anúncio ou avança clicando em CONTINUAR."""
        if watch_ads:
            return Action(
                action_type=ActionType.TAP,
                normalized_start=self.POSITIONS["X2_BITS_AD_BTN"],
                post_delay_ms=1500,
                metadata="Duplicar Bits (Assistir x2 BITS Ad)"
            )
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["CONTINUAR_GREEN_BTN"],
            post_delay_ms=1000,
            metadata="Avançar sem duplicar bits (Continuar)"
        )

    def plan_handle_mastery_boost(self) -> Action:
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["CONTINUAR_BOOST_BTN"],
            post_delay_ms=1000,
            metadata="Avançar Impulso de Maestria"
        )

    def plan_skip_bit_pack(self) -> Action:
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["TOQUE_PULAR_CENTER"],
            post_delay_ms=800,
            metadata="Toque para Pular (Abrir Bit Pack)"
        )

    def plan_unlock_new_unit(self) -> Action:
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["CONTINUAR_UNIT_BTN"],
            post_delay_ms=1000,
            metadata="Confirmar Desbloqueio de Nova Unidade"
        )

    def plan_close_ad(self, sub_element: Optional[str]) -> Action:
        """Encerra anúncios clicando no botão X de fechar ou no popup de recompensa."""
        if sub_element == "reward_granted":
            return Action(
                action_type=ActionType.TAP,
                normalized_start=self.POSITIONS["REWARD_GRANTED_CENTER"],
                post_delay_ms=800,
                metadata="Dispensar Popup de Recompensa Concedida"
            )
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["CLOSE_AD_X_BTN"],
            post_delay_ms=1000,
            metadata="Fechar Anúncio (Clicar no X)"
        )

    def plan_switch_to_battle_tab(self) -> Action:
        """Se estiver no menu de Coleção, clica na aba Batalha para retornar ao menu principal."""
        return Action(
            action_type=ActionType.TAP,
            normalized_start=self.POSITIONS["BATALHA_TAB"],
            post_delay_ms=1000,
            metadata="Navegar da Coleção para a aba Batalha"
        )
