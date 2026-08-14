import pytest

from src.strategy.unit_knowledge import (
    transformation_combat_factor,
    transformation_damage_rate_factor,
    transformation_tier,
)


@pytest.mark.parametrize(
    ("unit", "tier", "expected"),
    (
        ("Knight", 2, 1.2556),
        ("Knight", 3, 1.7609),
        ("Cupid", 2, 1.25),
        ("Cupid", 3, 1.75),
        ("Goose", 2, 1.4),
        ("Goose", 3, 1.7),
        ("Engineer", 2, 1.2389),
        ("Engineer", 3, 1.4875),
    ),
)
def test_transformation_factor_uses_prefab_mechanics(
    unit: str,
    tier: int,
    expected: float,
) -> None:
    assert transformation_combat_factor(unit, tier) == pytest.approx(
        expected, abs=0.001
    )


def test_goose_zombie_and_engineer_turret_facts_are_preserved() -> None:
    zombie = transformation_tier("Ganso", 2)
    elite_engineer = transformation_tier("Engenheiro", 3)

    assert zombie is not None
    assert zombie.unit_type == 11
    assert zombie.revive_health_multiplier == 0.4
    assert zombie.multiplier_min == 10
    assert elite_engineer is not None
    assert elite_engineer.unit_type == 91
    assert elite_engineer.summon_interval_seconds == 4.0
    assert elite_engineer.multiplier_min == 2


def test_direct_damage_rate_is_separate_from_resurrection_and_summoning() -> None:
    assert transformation_damage_rate_factor("Goose", 2) == pytest.approx(1.0)
    assert transformation_damage_rate_factor("Cupid", 2) == pytest.approx(1.5)
    assert transformation_damage_rate_factor("Knight", 3) == pytest.approx(
        1.5217, abs=0.001
    )
