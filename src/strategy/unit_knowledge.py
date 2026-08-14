from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UnitKnowledge:
    internal_name: str
    display_name: str
    aliases: tuple[str, ...]
    roles: frozenset[str]
    base_health: float
    base_damage: float
    early_spawn: int
    strategic_prior: float


# Grounded in Draft Showdown 1.14.1 UnitUpgradeSetup/DraftPool.  Roles and the
# small strategic priors are explicit policy judgement, informed by the current
# community role/counter guides; raw game values remain separate and auditable.
UNITS = (
    UnitKnowledge("Knight", "Cavaleiro", ("Knight", "Cavaleiro"), frozenset({"frontline", "tank"}), 95, 10, 3, 7),
    UnitKnowledge("Cupid", "Cupido", ("Cupid", "Cupido"), frozenset({"ranged"}), 35, 12, 3, -2),
    UnitKnowledge("Goose", "Ganso", ("Goose", "Ganso", "Gansos"), frozenset({"frontline", "swarm"}), 50, 10, 5, 5),
    UnitKnowledge("TNT", "TNT", ("TNT",), frozenset({"frontline", "area"}), 70, 75, 2, 4),
    UnitKnowledge("Snail", "Caracol", ("Snail", "Caracol"), frozenset({"ranged", "area"}), 130, 100, 1, 10),
    UnitKnowledge("Assassin", "Assassino", ("Assassin", "Assassino"), frozenset({"assassin"}), 28, 10, 3, -4),
    UnitKnowledge("Splime", "Splime", ("Splime", "Slimer"), frozenset({"frontline", "tanky_dps"}), 65, 15, 4, 0),
    UnitKnowledge("Kingclops", "Reiclops", ("Kingclops", "Reiclops"), frozenset({"tanky_dps"}), 100, 15, 1, -5),
    UnitKnowledge("Engineer", "Engenheiro", ("Engineer", "Engenheiro"), frozenset({"utility", "ranged"}), 150, 15, 1, 11),
)


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


# Own-team compatibility from the APK's DraftSynergySetup.  Values are -1, 0,
# or +1.  Only units currently unlocked/observed on this account are included;
# extending it is data work, not a policy rewrite.
_SYNERGY_ROWS = {
    "Knight": (0, 1, 0, 1, 0, 0, -1, 1, 0),
    "Cupid": (1, 0, 0, 1, 0, 0, 1, 0, -1),
    "Goose": (0, 0, 0, -1, 0, 0, -1, 1, 0),
    "TNT": (1, 1, -1, 0, 1, 0, 1, 1, 0),
    "Snail": (0, 0, 0, 1, 0, 0, 0, 0, -1),
    "Assassin": (0, 1, 0, 0, 1, 0, 0, -1, 1),
    "Splime": (-1, 1, -1, 1, 0, 0, 0, 1, 0),
    "Kingclops": (1, 0, 1, 1, 0, -1, 1, 0, -1),
    "Engineer": (0, 1, 0, 0, 1, -1, 0, -1, 0),
}


# Candidate-versus-opponent tendencies from the APK's AiTendencySetup.  This is
# the game's own draft signal: positive values favour the row unit into the
# visible opponent unit; negative values discourage it.
_COUNTER_ROWS = {
    "Knight": (0, 0, 12, 0, -60, 20, 0, 0, 0),
    "Cupid": (0, 0, -12, 30, -60, -20, 0, 60, -60),
    "Goose": (-20, 20, 0, -30, -60, 0, 0, 0, -60),
    "TNT": (0, -20, 12, 0, 0, 0, 15, 60, 60),
    "Snail": (0, 20, 12, 0, 0, -20, 15, 60, 0),
    "Assassin": (-20, 20, 0, 0, 60, 0, 0, 0, -60),
    "Splime": (0, 0, 0, -30, -60, 0, 0, -60, 0),
    "Kingclops": (20, -20, 12, 0, -60, 0, 15, 0, 0),
    "Engineer": (0, -20, 12, 30, 0, 20, 0, 0, 60),
}

_ORDER = tuple(unit.internal_name for unit in UNITS)


def synergy(candidate: str | None, ally: str | None) -> int:
    candidate_unit = unit_for(candidate)
    ally_unit = unit_for(ally)
    if candidate_unit is None or ally_unit is None:
        return 0
    return _SYNERGY_ROWS[candidate_unit.internal_name][
        _ORDER.index(ally_unit.internal_name)
    ]


def counter_tendency(candidate: str | None, opponent: str | None) -> int:
    candidate_unit = unit_for(candidate)
    opponent_unit = unit_for(opponent)
    if candidate_unit is None or opponent_unit is None:
        return 0
    return _COUNTER_ROWS[candidate_unit.internal_name][
        _ORDER.index(opponent_unit.internal_name)
    ]
