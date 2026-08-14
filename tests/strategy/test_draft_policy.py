from src.strategy.draft_policy import DraftPolicy
from src.vision.draft_reader import DraftCard, DraftCardReader
from src.device.profile_reader import AccountSnapshot


def test_reader_parses_observed_portuguese_card_effects() -> None:
    add = DraftCardReader._parse(0, ("5", "+3 Cupido"), (1.0, 0.99))
    multiply = DraftCardReader._parse(2, ("5", "Cavaleiro x2"), (1.0, 0.98))
    upgrade = DraftCardReader._parse(1, ("Ganso zumbi!",), (0.97,))

    assert (add.unit, add.effect, add.magnitude) == ("Cupido", "add", 3)
    assert (multiply.unit, multiply.effect, multiply.magnitude) == (
        "Cavaleiro",
        "multiply",
        2,
    )
    assert (upgrade.unit, upgrade.effect) == ("Ganso", "upgrade")


def test_policy_prefers_high_value_effect_and_is_deterministic() -> None:
    cards = (
        DraftCard(0, "+1 Engenheiro", "Engenheiro", "add", 1, 0.99),
        DraftCard(1, "+3 Cupido", "Cupido", "add", 3, 0.99),
        DraftCard(2, "Cavaleiro x2", "Cavaleiro", "multiply", 2, 0.99),
    )
    policy = DraftPolicy()
    first = policy.choose(cards, history={"Cavaleiro": 3}, variant="normal_pick")
    second = policy.choose(cards, history={"Cavaleiro": 3}, variant="normal_pick")

    assert first == second
    assert first.selected_slot == 1
    assert "tabela IA por contagem APK" in first.reason


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


def test_policy_uses_tnt_as_the_apk_counter_to_visible_geese() -> None:
    cards = (
        DraftCard(0, "+5 Ganso", "Ganso", "add", 5, 0.99),
        DraftCard(1, "+2 TNT", "TNT", "add", 2, 0.99),
    )

    decision = DraftPolicy().choose(
        cards,
        history={"Cavaleiro": 3},
        variant="normal_pick",
        enemy_units=("Goose",),
        enemy_pressure="high",
    )

    assert decision.selected_slot == 1
    assert "resposta aos picks inimigos" in decision.reason


def test_policy_multiplies_a_mass_of_fifteen_geese() -> None:
    cards = (
        DraftCard(0, "Ganso x2", "Ganso", "multiply", 2, 0.99),
        DraftCard(1, "+1 Engenheiro", "Engenheiro", "add", 1, 0.99),
        DraftCard(2, "+2 TNT", "TNT", "add", 2, 0.99),
    )

    decision = DraftPolicy().choose(
        cards,
        history={"Ganso": 15, "Cavaleiro": 3},
        variant="normal_pick",
        enemy_units=("Knight",),
    )

    assert decision.selected_slot == 0
    assert "tabela IA por contagem APK 1.14.1 (15 em campo) +50.0" in decision.reason


def test_policy_infers_an_opening_group_from_a_multiplier_offer() -> None:
    cards = (
        DraftCard(0, "Ganso x2", "Ganso", "multiply", 2, 0.99),
        DraftCard(1, "+5 Ganso", "Ganso", "add", 5, 0.99),
    )

    decision = DraftPolicy().choose(cards, history={}, variant="normal_pick")

    assert decision.selected_slot == 0
    assert "contagem inicial inferida da carta: 5 Ganso" in decision.reason


def test_policy_recognizes_history_aliases_when_applying_count_rules() -> None:
    cards = (DraftCard(0, "Goose x2", "Goose", "multiply", 2, 0.99),)

    decision = DraftPolicy().choose(
        cards,
        history={"Ganso": 20},
        variant="normal_pick",
    )

    assert "(20 em campo) +100.0" in decision.reason


def test_policy_uses_the_real_account_level_read_from_adb() -> None:
    account = AccountSnapshot(
        levels={"Engenheiro": 5},
        mastery_points={"Engenheiro": 283},
        resources={},
        matches=0,
        wins=0,
        losses=0,
        unit_stats={},
        shop={},
        read_at_monotonic=1.0,
    )
    card = DraftCard(0, "+1 Engenheiro", "Engenheiro", "add", 1, 0.99)

    decision = DraftPolicy(account).choose(
        (card,), history={}, variant="normal_pick"
    )

    assert "progressão ADB Nv.5 (1.464x stats) +9.3" in decision.reason
    assert "maestria ADB 283 pontos" in decision.reason


def test_policy_values_a_multiplier_at_the_tracked_transformed_tier() -> None:
    card = DraftCard(0, "Gansos avanÃ§ados x2", "Ganso", "multiply", 2, 0.99)

    decision = DraftPolicy().choose(
        (card,),
        history={"Goose": 10},
        tiers={"Goose": 2},
        variant="normal_pick",
    )

    assert "tier 2 (advanced_zombie, valor corporal 1.40x)" in decision.reason
    assert "~700 vida" in decision.reason


def test_policy_calculates_the_incremental_value_of_an_upgrade() -> None:
    card = DraftCard(0, "Ganso zumbi!", "Ganso", "upgrade", 1, 0.99)

    decision = DraftPolicy().choose(
        (card,),
        history={"Goose": 10},
        tiers={"Goose": 1},
        variant="normal_pick",
    )

    assert "tier 1->2: valor 1.00x->1.40x" in decision.reason
    assert "Revives once after death with 40% Health and Damage." in decision.reason
