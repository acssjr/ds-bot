from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from importlib.resources import files
from typing import Any


def _load_game_data() -> dict[str, Any]:
    resource = files("src.strategy.data").joinpath("game_data_1_14_1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


GAME_DATA = _load_game_data()
GAME_DATA_VERSION = str(GAME_DATA["apk_version"])


@dataclass(frozen=True, slots=True)
class UnitKnowledge:
    internal_name: str
    display_name: str
    aliases: tuple[str, ...]
    roles: frozenset[str]
    base_health: float
    base_damage: float
    stat_multiplier_per_level: float
    early_spawn: int
    late_spawn: int
    move_speed: float
    attack_range: float
    attack_cycle_seconds: float | None
    direct_damage_events_per_cycle: int
    behaviour: tuple[tuple[str, int | float], ...]
    community_tier: str
    strategic_prior: float


@dataclass(frozen=True, slots=True)
class TransformationTier:
    unit: str
    tier: int
    label: str
    unit_type: int
    health_multiplier: float
    damage_multiplier: float
    attack_cycle_seconds: float | None
    damage_events_per_cycle: int
    move_speed: float
    revive_health_multiplier: float
    revive_damage_multiplier: float
    summon_interval_seconds: float | None
    multiplier_min: int
    multiplier_max: int
    description: str
    source_conflict: str | None
    declared_damage_rate_multiplier: float | None


# These labels are policy metadata, kept apart from the APK facts below.  The
# tier snapshot is the community list supplied on 2026-08-14; its deliberately
# small prior can break close ties but cannot override the game's count/counter
# tables. Names such as Spartheus and Merlinor are tier-III forms of the base
# units Spartan and Wizard.
_POLICY = {
    "Knight": ("Cavaleiro", ("Knight", "Cavaleiro"), {"frontline", "tank"}, "B+", 1),
    "Cupid": ("Cupido", ("Cupid", "Cupido"), {"ranged"}, "A", 7),
    "Goose": ("Ganso", ("Goose", "Ganso", "Gansos"), {"frontline", "swarm"}, "A", 7),
    "TNT": ("TNT", ("TNT",), {"frontline", "area", "suicide"}, "A", 7),
    "Snail": ("Caracol", ("Snail", "Caracol"), {"ranged", "area"}, "A", 7),
    "Assassin": ("Assassino", ("Assassin", "Assassino"), {"assassin"}, "C", -3),
    "Splime": ("Splime", ("Splime", "Slimer"), {"frontline", "tanky_dps"}, "A", 7),
    "Kingclops": ("Reiclops", ("Kingclops", "Reiclops"), {"tanky_dps"}, "D", -5),
    "Waster": ("Waster", ("Waster",), {"frontline", "area"}, "A-", 4),
    "Beetank": ("Beetank", ("Beetank",), {"tank", "summoner"}, "B+", 1),
    "Mole": ("Mole", ("Mole",), {"frontline", "assassin"}, "B+", 1),
    "Sniper": ("Sniper", ("Sniper",), {"ranged"}, "A-", 4),
    "Wizard": ("Merlinor", ("Wizard", "Merlinor"), {"ranged", "area"}, "A", 7),
    "Turtle": ("Shellbro", ("Turtle", "Shellbro"), {"tank", "assassin"}, "A", 7),
    "Spartan": ("Spartheus", ("Spartan", "Spartheus"), {"frontline", "tank"}, "A+", 10),
    "Parasite": ("Parasite", ("Parasite",), {"frontline", "tanky_dps"}, "A-", 4),
    "Cowboy": ("Sixshoot", ("Cowboy", "Sixshoot"), {"ranged"}, "A-", 4),
    "ManEater": ("Bloodvine", ("ManEater", "Bloodvine"), {"frontline", "tank"}, "A-", 4),
    "Agent": ("Agent B", ("Agent", "Agent B"), {"ranged", "assassin"}, "A+", 10),
    "Villain": ("Overmind", ("Villain", "Overmind"), {"ranged", "area"}, "A", 7),
    "Goblin": ("Boomling", ("Goblin", "Boomling"), {"ranged", "area"}, "A", 7),
    "Totem": ("Totem", ("Totem",), {"ranged", "support"}, "A-", 4),
    "Engineer": ("Engenheiro", ("Engineer", "Engenheiro"), {"utility", "summoner"}, "A", 7),
    "Spider": ("Matriarch", ("Spider", "Matriarch"), {"frontline", "summoner"}, "A", 7),
    "Dragon": ("Whelp", ("Dragon", "Whelp"), {"frontline", "flying"}, "A+", 10),
}


def _unit(name: str) -> UnitKnowledge:
    facts = GAME_DATA["units"][name]
    display, aliases, roles, tier, prior = _POLICY[name]
    animation = facts.get("attack_animation")
    return UnitKnowledge(
        name,
        display,
        tuple(aliases),
        frozenset(roles),
        float(facts["health"]),
        float(facts["damage"]),
        float(facts["stat_multiplier_per_level"]),
        int(facts["spawn_early"]),
        int(facts["spawn_late"]),
        float(facts["move_speed"]),
        float(facts["attack_range"]),
        float(animation["cycle_seconds"]) if animation else None,
        sum(
            1
            for event in (animation or {}).get("events", ())
            if event.get("name") in {"OnAttack", "OnShoot"}
        ),
        tuple(sorted(facts.get("behaviour", {}).items())),
        tier,
        float(prior),
    )


UNITS = tuple(_unit(name) for name in GAME_DATA["unit_order"])


def _key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).casefold()


_BY_ALIAS = {
    _key(alias): unit
    for unit in UNITS
    for alias in (unit.internal_name, unit.display_name, *unit.aliases)
}


def unit_for(value: str | None) -> UnitKnowledge | None:
    if not value:
        return None
    normalized = _key(value)
    direct = _BY_ALIAS.get(normalized)
    if direct is not None:
        return direct
    return next(
        (unit for alias, unit in _BY_ALIAS.items() if alias in normalized),
        None,
    )


def synergy(candidate: str | None, ally: str | None) -> int:
    candidate_unit = unit_for(candidate)
    ally_unit = unit_for(ally)
    if candidate_unit is None or ally_unit is None:
        return 0
    return int(
        GAME_DATA["synergy"][candidate_unit.internal_name][ally_unit.internal_name]
    )


def counter_tendency(candidate: str | None, opponent: str | None) -> int:
    candidate_unit = unit_for(candidate)
    opponent_unit = unit_for(opponent)
    if candidate_unit is None or opponent_unit is None:
        return 0
    return int(
        GAME_DATA["counter_tendency"][candidate_unit.internal_name][
            opponent_unit.internal_name
        ]
    )


def unit_count_tendency(
    effect: str,
    *,
    spawn_group: int,
    current_count: int,
) -> int:
    """Return the exact AiUnitCountSetup value, clamped to its 0..24 domain."""

    suffix = {
        "add": "Spawn Early",
        "multiply": "Multiplier",
        "upgrade": "Upgrade",
    }.get(effect)
    if suffix is None:
        return 0
    group = min(5, max(1, int(spawn_group)))
    count = min(24, max(0, int(current_count)))
    return int(GAME_DATA["unit_count_scores"][f"x{group} {suffix}"][count])


def transformation_tier(
    unit: str | None,
    tier: int = 1,
) -> TransformationTier | None:
    """Return the APK-backed tier for a base unit family."""

    knowledge = unit_for(unit)
    if knowledge is None:
        return None
    family = GAME_DATA.get("transformations", {}).get(knowledge.internal_name)
    if not family:
        return None
    normalized_tier = min(3, max(1, int(tier)))
    raw = next(
        (entry for entry in family["tiers"] if entry["tier"] == normalized_tier),
        None,
    )
    if raw is None:
        return None
    return TransformationTier(
        unit=knowledge.internal_name,
        tier=int(raw["tier"]),
        label=str(raw["label"]),
        unit_type=int(raw["unit_type"]),
        health_multiplier=float(raw["health_multiplier"]),
        damage_multiplier=float(raw["damage_multiplier"]),
        attack_cycle_seconds=(
            float(raw["attack_cycle_seconds"])
            if raw.get("attack_cycle_seconds") is not None
            else None
        ),
        damage_events_per_cycle=int(raw.get("damage_events_per_cycle", 0)),
        move_speed=float(raw.get("move_speed", knowledge.move_speed)),
        revive_health_multiplier=float(raw.get("revive_health_multiplier", 0.0)),
        revive_damage_multiplier=float(raw.get("revive_damage_multiplier", 0.0)),
        summon_interval_seconds=(
            float(raw["summon_interval_seconds"])
            if raw.get("summon_interval_seconds") is not None
            else None
        ),
        multiplier_min=int(raw["multiplier_min"]),
        multiplier_max=int(raw["multiplier_max"]),
        description=str(raw.get("description", "Base unit.")),
        source_conflict=(
            str(raw["source_conflict"]) if raw.get("source_conflict") else None
        ),
        declared_damage_rate_multiplier=(
            float(raw["declared_damage_rate_multiplier"])
            if raw.get("declared_damage_rate_multiplier") is not None
            else None
        ),
    )


def transformation_combat_factor(unit: str | None, tier: int = 1) -> float:
    """Estimate whole-life body value from explicit APK tier mechanics.

    Health exposure and damage throughput receive equal weight. Resurrection,
    mobility and summoning are added from their concrete prefab parameters;
    counter/synergy tables remain separate policy inputs.
    """

    current = transformation_tier(unit, tier)
    base = transformation_tier(unit, 1)
    if current is None or base is None:
        return 1.0
    damage_rate = transformation_damage_rate_factor(unit, tier)
    health_exposure = current.health_multiplier + current.revive_health_multiplier
    damage_exposure = damage_rate + current.revive_damage_multiplier
    value = (health_exposure + damage_exposure) / 2.0
    if current.move_speed > base.move_speed > 0:
        value += 0.10 * (current.move_speed / base.move_speed - 1.0)
    if (
        current.summon_interval_seconds
        and base.summon_interval_seconds
        and current.summon_interval_seconds > 0
    ):
        value += 0.35 * (
            base.summon_interval_seconds / current.summon_interval_seconds - 1.0
        )
    return value


def transformation_damage_rate_factor(unit: str | None, tier: int = 1) -> float:
    """Return direct damage-event throughput, excluding lifetime abilities."""

    current = transformation_tier(unit, tier)
    base = transformation_tier(unit, 1)
    if current is None or base is None:
        return 1.0
    if current.declared_damage_rate_multiplier is not None:
        return current.declared_damage_rate_multiplier
    if (
        current.attack_cycle_seconds
        and current.damage_events_per_cycle
        and base.attack_cycle_seconds
        and base.damage_events_per_cycle
    ):
        return current.damage_multiplier * (
            current.damage_events_per_cycle / current.attack_cycle_seconds
        ) / (base.damage_events_per_cycle / base.attack_cycle_seconds)
    return current.damage_multiplier
