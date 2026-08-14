from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

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
    """Deterministic, explainable first-pass utility policy.

    It uses only observed card facts. No invented card tier or hidden game rule is
    treated as truth; those can be added later from measured battle outcomes.
    """

    def choose(
        self,
        cards: Iterable[DraftCard],
        *,
        history: Mapping[str, int],
        variant: str,
    ) -> DraftDecision:
        card_list = tuple(cards)
        if not card_list:
            raise ValueError("at least one draft card is required")
        distinct_units = len(history)
        scored: list[ScoredDraftCard] = []
        for card in card_list:
            score = 10.0
            reasons = ["slot visualmente disponível +10"]
            if card.unit is not None:
                score += 15.0
                reasons.append(f"unidade reconhecida ({card.unit}) +15")
            effect_bonus = {
                "add": 9.0 * card.magnitude,
                "multiply": 20.0 + 8.0 * max(1, card.magnitude - 1),
                "upgrade": 22.0,
                "transform": 18.0,
                "unknown": 0.0,
            }[card.effect]
            score += effect_bonus
            if effect_bonus:
                reasons.append(f"efeito {card.effect} +{effect_bonus:.0f}")

            owned = history.get(card.unit, 0) if card.unit is not None else 0
            if owned:
                continuity = min(15.0, owned * 5.0)
                score += continuity
                reasons.append(f"continuidade com presença estimada {owned} +{continuity:.0f}")
                if card.effect == "upgrade":
                    score += 15.0
                    reasons.append("upgrade aplicado a unidade já escolhida +15")
            elif card.unit is not None and distinct_units < 4:
                score += 8.0
                reasons.append("diversidade inicial do exército +8")

            confidence_bonus = card.confidence * 5.0
            score += confidence_bonus
            reasons.append(f"confiança OCR +{confidence_bonus:.1f}")
            if variant == "recovery_bonus" and card.effect in {"add", "multiply"}:
                score += 5.0
                reasons.append("prioridade de recuperação por volume +5")
            scored.append(ScoredDraftCard(card, score, tuple(reasons)))

        # Higher score wins. Slot number is only a deterministic final tie-breaker.
        ranked = tuple(sorted(scored, key=lambda item: (-item.score, item.card.slot)))
        winner = ranked[0]
        reason = "; ".join(winner.reasons)
        return DraftDecision(winner.card.slot, winner.card.text, winner.score, reason, ranked)
