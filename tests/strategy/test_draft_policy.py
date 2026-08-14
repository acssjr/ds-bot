from src.strategy.draft_policy import DraftPolicy
from src.vision.draft_reader import DraftCard, DraftCardReader


def test_reader_parses_observed_portuguese_card_effects() -> None:
    add = DraftCardReader._parse(0, ("5", "+3 Cupido"), (1.0, 0.99))
    multiply = DraftCardReader._parse(2, ("5", "Cavaleiro x2"), (1.0, 0.98))
    transform = DraftCardReader._parse(1, ("Ganso zumbi!",), (0.97,))

    assert (add.unit, add.effect, add.magnitude) == ("Cupido", "add", 3)
    assert (multiply.unit, multiply.effect, multiply.magnitude) == ("Cavaleiro", "multiply", 2)
    assert (transform.unit, transform.effect) == ("Ganso", "transform")


def test_policy_prefers_high_value_effect_and_is_deterministic() -> None:
    cards = (
        DraftCard(0, "+1 Engenheiro", "Engenheiro", "add", 1, 0.99),
        DraftCard(1, "+3 Cupido", "Cupido", "add", 3, 0.99),
        DraftCard(2, "Cavaleiro x2", "Cavaleiro", "multiply", 2, 0.99),
    )
    policy = DraftPolicy()
    first = policy.choose(cards, history={}, variant="normal_pick")
    second = policy.choose(cards, history={}, variant="normal_pick")

    assert first == second
    assert first.selected_slot == 2
    assert "multiply" in first.reason


def test_policy_reinforces_a_valid_upgrade_for_existing_unit() -> None:
    cards = (
        DraftCard(0, "Cupido UP!", "Cupido", "upgrade", 1, 0.99),
        DraftCard(1, "+3 Ganso", "Ganso", "add", 3, 0.99),
    )
    decision = DraftPolicy().choose(
        cards,
        history={"Cupido": 2},
        variant="normal_pick",
    )
    assert decision.selected_slot == 0
    assert "unidade já escolhida" in decision.reason
