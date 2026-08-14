from src.strategy.unit_knowledge import (
    GAME_DATA,
    GAME_DATA_VERSION,
    UNITS,
    counter_tendency,
    synergy,
    unit_count_tendency,
    unit_for,
)


def test_versioned_apk_data_covers_all_draft_units_and_matrices() -> None:
    assert GAME_DATA_VERSION == "1.14.1"
    assert len(UNITS) == 25
    assert set(GAME_DATA["synergy"]) == {unit.internal_name for unit in UNITS}
    assert all(len(row) == 25 for row in GAME_DATA["synergy"].values())
    assert all(len(row) == 25 for row in GAME_DATA["counter_tendency"].values())


def test_engineer_serialized_facts_explain_the_assassin_counter() -> None:
    engineer = unit_for("Engenheiro")
    assassin = unit_for("Assassino")

    assert engineer is not None and assassin is not None
    assert engineer.move_speed == 2
    assert assassin.move_speed == 5
    assert dict(engineer.behaviour) == {
        "firstSpawnDelay": 1.5,
        "spawnDelay": 5,
        "spawnDelayRandom": 0.2,
    }
    assert dict(assassin.behaviour)["teleportWaitDelay"] == 1
    assert counter_tendency("Engineer", "Assassin") == 20


def test_tnt_goose_and_fifteen_unit_count_rules_are_exact_apk_values() -> None:
    assert counter_tendency("TNT", "Goose") == 12
    assert synergy("TNT", "Goose") == -1
    assert unit_count_tendency("multiply", spawn_group=5, current_count=15) == 500
    assert unit_count_tendency("add", spawn_group=5, current_count=15) == 200
    assert unit_count_tendency("upgrade", spawn_group=5, current_count=15) == 0


def test_count_table_is_bounded_for_large_armies() -> None:
    assert unit_count_tendency("multiply", spawn_group=5, current_count=999) == 0
    assert unit_count_tendency("upgrade", spawn_group=5, current_count=999) == 1000
