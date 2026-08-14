from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from src.strategy.unit_knowledge import (
    GAME_DATA_VERSION,
    counter_tendency,
    synergy,
    transformation_combat_factor,
    transformation_damage_rate_factor,
    transformation_tier,
    unit_count_tendency,
    unit_for,
)
from src.vision.draft_reader import DraftCard
from src.device.profile_reader import AccountSnapshot


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

    def __init__(self, account: AccountSnapshot | None = None) -> None:
        self._account = account

    def choose(
        self,
        cards: Iterable[DraftCard],
        *,
        history: Mapping[str, int],
        variant: str,
        tiers: Mapping[str, int] | None = None,
        enemy_units: Iterable[str] = (),
        enemy_pressure: str = "unknown",
    ) -> DraftDecision:
        card_list = tuple(cards)
        if not card_list:
            raise ValueError("at least one draft card is required")
        distinct_units = len(history)
        enemy_list = tuple(dict.fromkeys(str(unit) for unit in enemy_units))
        tier_history = tiers or {}
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

            account_level = self._account.level_for(card.unit) if self._account else 1
            mastery_points = self._account.mastery_for(card.unit) if self._account else 0
            stat_factor = (
                knowledge.stat_multiplier_per_level ** (account_level - 1)
                if knowledge is not None
                else 1.0
            )
            if account_level > 1:
                progression_bonus = (stat_factor - 1.0) * 20.0
                score += progression_bonus
                reasons.append(
                    f"progressão ADB Nv.{account_level} ({stat_factor:.3f}x stats) "
                    f"+{progression_bonus:.1f}"
                )
            if mastery_points:
                reasons.append(f"maestria ADB {mastery_points} pontos")

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
            current_tier = 1
            if knowledge is not None:
                current_tier = max(
                    (
                        int(value)
                        for name, value in tier_history.items()
                        if (tier_unit := unit_for(name)) is not None
                        and tier_unit.internal_name == knowledge.internal_name
                    ),
                    default=1,
                )
                current_tier = min(3, max(1, current_tier))
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
            tier_factor = transformation_combat_factor(card.unit, current_tier)
            base_body_value = (
                min(
                    4.0,
                    knowledge.base_health * stat_factor / 100.0
                    + knowledge.base_damage * stat_factor / 50.0,
                )
                if knowledge is not None
                else 1.0
            )
            body_value = base_body_value * tier_factor
            normalized_effect = (
                "upgrade" if card.effect == "transform" else card.effect
            )
            effect_bonus = {
                "add": 4.0 + body_value * card.magnitude,
                "multiply": (
                    16.0
                    + body_value * owned * max(1, card.magnitude - 1)
                    if owned
                    else -10.0
                ),
                "upgrade": 10.0 if owned else 3.0,
                "transform": 10.0 if owned else 3.0,
                "unknown": 0.0,
            }[card.effect]
            score += effect_bonus
            if effect_bonus:
                reasons.append(f"valor do efeito {card.effect} {effect_bonus:+.1f}")

            if knowledge is not None:
                count_tendency = unit_count_tendency(
                    normalized_effect,
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
                if card.effect == "multiply" and owned:
                    added_units = owned * max(1, card.magnitude - 1)
                    added_health = knowledge.base_health * stat_factor * added_units
                    active_tier = transformation_tier(card.unit, current_tier)
                    if active_tier is not None:
                        added_health *= (
                            active_tier.health_multiplier
                            + active_tier.revive_health_multiplier
                        )
                        reasons.append(
                            f"x{card.magnitude} duplica tier {active_tier.tier} "
                            f"({active_tier.label}, valor corporal {tier_factor:.2f}x)"
                        )
                    cycle = knowledge.attack_cycle_seconds
                    hits = knowledge.direct_damage_events_per_cycle
                    if cycle and hits:
                        added_dps = (
                            knowledge.base_damage
                            * stat_factor
                            * hits
                            / cycle
                            * added_units
                            * transformation_damage_rate_factor(
                                card.unit, current_tier
                            )
                        )
                        reasons.append(
                            f"x{card.magnitude} adiciona {added_units} corpo(s): "
                            f"~{added_health:.0f} vida e ~{added_dps:.0f} DPS direto "
                            "antes de habilidades"
                        )
                    else:
                        reasons.append(
                            f"x{card.magnitude} adiciona {added_units} corpo(s): "
                            f"~{added_health:.0f} vida; dano depende da habilidade especial"
                        )
                    if "summoner" in knowledge.roles:
                        reasons.append(
                            "duplicação também multiplica invocadores; unidades geradas "
                            "não estão incluídas no DPS estimado"
                        )
                if normalized_effect == "upgrade" and owned:
                    if current_tier >= 3:
                        score -= 30.0
                        reasons.append("tier elite jÃ¡ rastreado; upgrade inconsistente -30")
                    else:
                        next_tier = current_tier + 1
                        next_factor = transformation_combat_factor(card.unit, next_tier)
                        gain = max(0.0, next_factor - tier_factor)
                        transformation_bonus = owned * gain * base_body_value * 4.0
                        score += transformation_bonus
                        next_data = transformation_tier(card.unit, next_tier)
                        reasons.append(
                            f"evolui {owned} corpo(s) tier {current_tier}->{next_tier}: "
                            f"valor {tier_factor:.2f}x->{next_factor:.2f}x "
                            f"+{transformation_bonus:.1f}"
                        )
                        if next_data is not None:
                            reasons.append(next_data.description)
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
                if normalized_effect == "upgrade":
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
