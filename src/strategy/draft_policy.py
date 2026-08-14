from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.strategy.unit_knowledge import (
    GAME_DATA_VERSION,
    counter_tendency,
    synergy,
    unit_count_tendency,
    unit_for,
)
from src.vision.draft_reader import DraftCard


@dataclass(frozen=True, slots=True)
class ScoredDraftCard:
    card: DraftCard
    score: float
    reasons: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return {
            **self.card.payload(),
            "score": round(self.score, 2),
            "reasons": self.reasons,
        }


@dataclass(frozen=True, slots=True)
class DraftDecision:
    selected_slot: int
    selected_text: str
    score: float
    reason: str
    candidates: tuple[ScoredDraftCard, ...]

    def payload(self) -> dict[str, object]:
        return {
            "selected_slot": self.selected_slot,
            "selected_text": self.selected_text,
            "selected_score": round(self.score, 2),
            "reason": self.reason,
            "candidates": tuple(candidate.payload() for candidate in self.candidates),
        }


class DraftPolicy:
    """Explainable policy grounded in game data, composition, and opposition."""

    def choose(
        self,
        cards: Iterable[DraftCard],
        *,
        history: Mapping[str, int],
        variant: str,
        enemy_units: Iterable[str] = (),
        enemy_pressure: str = "unknown",
    ) -> DraftDecision:
        card_list = tuple(cards)
        if not card_list:
            raise ValueError("at least one draft card is required")
        distinct_units = len(history)
        enemy_list = tuple(dict.fromkeys(str(unit) for unit in enemy_units))
        owned_roles = {
            role
            for name, count in history.items()
            if count > 0 and (knowledge := unit_for(name)) is not None
            for role in knowledge.roles
        }

        scored: list[ScoredDraftCard] = []
        for card in card_list:
            score = 10.0
            reasons = ["slot visualmente disponível +10"]
            knowledge = unit_for(card.unit)
            if card.unit is not None:
                score += 10.0
                reasons.append(f"unidade reconhecida ({card.unit}) +10")

            tracked_owned = (
                sum(
                    count
                    for name, count in history.items()
                    if knowledge is not None
                    and (owned_unit := unit_for(name)) is not None
                    and owned_unit.internal_name == knowledge.internal_name
                )
                if knowledge is not None
                else history.get(card.unit, 0) if card.unit is not None else 0
            )
            owned = tracked_owned
            if (
                owned == 0
                and knowledge is not None
                and card.effect in {"multiply", "upgrade", "transform"}
            ):
                # The game does not offer these effects for a truly absent
                # unit.  When observation starts mid-battle, the card itself
                # is evidence of at least the unit's normal opening group.
                owned = knowledge.early_spawn
                reasons.append(
                    f"contagem inicial inferida da carta: {owned} {knowledge.display_name}"
                )
            body_value = (
                min(
                    4.0,
                    knowledge.base_health / 100.0 + knowledge.base_damage / 50.0,
                )
                if knowledge is not None
                else 1.0
            )
            effect_bonus = {
                "add": 4.0 + body_value * card.magnitude,
                "multiply": (
                    16.0
                    + body_value * owned * max(1, card.magnitude - 1)
                    if owned
                    else -10.0
                ),
                "upgrade": 20.0 if owned else 3.0,
                "transform": 14.0 if owned else 2.0,
                "unknown": 0.0,
            }[card.effect]
            score += effect_bonus
            if effect_bonus:
                reasons.append(f"valor do efeito {card.effect} {effect_bonus:+.1f}")

            if knowledge is not None:
                count_tendency = unit_count_tendency(
                    card.effect,
                    spawn_group=knowledge.early_spawn,
                    current_count=owned,
                )
                count_bonus = count_tendency / 10.0
                if count_bonus:
                    score += count_bonus
                    reasons.append(
                        f"tabela IA por contagem APK {GAME_DATA_VERSION} "
                        f"({owned} em campo) {count_bonus:+.1f}"
                    )
                score += knowledge.strategic_prior
                if knowledge.strategic_prior:
                    reasons.append(
                        f"prioridade estratégica {knowledge.strategic_prior:+.0f}"
                    )
                missing_role_bonus = 0.0
                if "frontline" not in owned_roles and "frontline" in knowledge.roles:
                    missing_role_bonus += 8.0
                if "ranged" not in owned_roles and "ranged" in knowledge.roles:
                    missing_role_bonus += 7.0
                if (
                    distinct_units >= 2
                    and "utility" not in owned_roles
                    and "utility" in knowledge.roles
                ):
                    missing_role_bonus += 5.0
                if missing_role_bonus:
                    score += missing_role_bonus
                    reasons.append(f"cobre papel ausente +{missing_role_bonus:.0f}")

            if owned:
                continuity = min(12.0, owned * 2.5)
                score += continuity
                reasons.append(f"continuidade com {owned} unidade(s) +{continuity:.1f}")
                if card.effect == "upgrade":
                    score += 12.0
                    reasons.append("upgrade aplicado a unidade já escolhida +12")

            if knowledge is not None:
                synergy_score = sum(
                    synergy(knowledge.internal_name, ally) * 4.0
                    for ally, count in history.items()
                    if count > 0
                )
                if synergy_score:
                    score += synergy_score
                    reasons.append(f"sinergia oficial do draft {synergy_score:+.0f}")

                counter_score = sum(
                    counter_tendency(knowledge.internal_name, enemy) / 6.0
                    for enemy in enemy_list
                )
                if counter_score:
                    score += counter_score
                    reasons.append(
                        f"resposta aos picks inimigos {counter_score:+.1f}"
                    )

                pressure_bonus = 0.0
                if enemy_pressure == "high":
                    if "area" in knowledge.roles:
                        pressure_bonus += 8.0
                    if "frontline" in knowledge.roles or "tank" in knowledge.roles:
                        pressure_bonus += 4.0
                elif enemy_pressure == "moderate" and "area" in knowledge.roles:
                    pressure_bonus += 4.0
                if pressure_bonus:
                    score += pressure_bonus
                    reasons.append(
                        f"adaptação à pressão visual inimiga +{pressure_bonus:.0f}"
                    )

            confidence_bonus = card.confidence * 5.0
            score += confidence_bonus
            reasons.append(f"confiança OCR +{confidence_bonus:.1f}")
            if variant == "recovery_bonus" and card.effect in {"add", "multiply"}:
                score += 5.0
                reasons.append("prioridade de recuperação por volume +5")
            scored.append(ScoredDraftCard(card, score, tuple(reasons)))

        ranked = tuple(sorted(scored, key=lambda item: (-item.score, item.card.slot)))
        winner = ranked[0]
        reason = "; ".join(winner.reasons)
        return DraftDecision(
            winner.card.slot,
            winner.card.text,
            winner.score,
            reason,
            ranked,
        )
