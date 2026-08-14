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
    early_spawn: int
    late_spawn: int
    move_speed: float
    attack_range: float
    attack_cycle_seconds: float | None
    behaviour: tuple[tuple[str, int | float], ...]
    community_tier: str
    strategic_prior: float


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
        int(facts["spawn_early"]),
        int(facts["spawn_late"]),
        float(facts["move_speed"]),
        float(facts["attack_range"]),
        float(animation["cycle_seconds"]) if animation else None,
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
