from __future__ import annotations

import base64
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.device.session import DeviceSession
from src.strategy.unit_knowledge import unit_for


_PACKAGE = "com.QuestLab.DraftWar"
_PROFILE_NAMES = (
    "CardLevelsProfileData",
    "UnitMasteryProfileData",
    "ResourcesProfileData",
    "MatchStatsProfileData",
    "ShopProfileData",
)
_SAFE_PROFILE_PATH = re.compile(
    r"^/sdcard/Android/data/com\.QuestLab\.DraftWar/files/NakamaLocal_[^/]+$"
)


def _integer(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _unit_name(raw: object) -> str | None:
    name = re.sub(r"\d+$", "", str(raw or ""))
    knowledge = unit_for(name)
    return knowledge.display_name if knowledge is not None else (name or None)


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    levels: Mapping[str, int]
    mastery_points: Mapping[str, int]
    resources: Mapping[str, int]
    matches: int
    wins: int
    losses: int
    unit_stats: Mapping[str, Mapping[str, int]]
    shop: Mapping[str, Any]
    read_at_monotonic: float

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.matches if self.matches > 0 else None

    def level_for(self, unit: str | None) -> int:
        knowledge = unit_for(unit)
        if knowledge is None:
            return 1
        return int(self.levels.get(knowledge.display_name, 1))

    def mastery_for(self, unit: str | None) -> int:
        knowledge = unit_for(unit)
        if knowledge is None:
            return 0
        return int(self.mastery_points.get(knowledge.display_name, 0))

    def resource_payload(self) -> dict[str, Any]:
        units = []
        for name, level in self.levels.items():
            stats = self.unit_stats.get(name, {})
            units.append(
                {
                    "name": name,
                    "level": level,
                    "mastery_points": self.mastery_points.get(name, 0),
                    "uses": int(stats.get("uses", 0)),
                    "wins": int(stats.get("wins", 0)),
                }
            )
        units.sort(key=lambda item: (-item["uses"], -item["level"], item["name"]))
        return {
            "coins": self.resources.get("coins"),
            "trophies": self.resources.get("trophies"),
            "gems": self.resources.get("gems"),
            "mastery_currency": self.resources.get("mastery_currency"),
            "units": tuple(units),
            "matches": self.matches,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "resource_source": "adb_profile",
        }


class AdbProfileReader:
    """Read the game's local Nakama cache without navigating or taking screenshots."""

    def __init__(self, session: DeviceSession, *, clock=time.monotonic) -> None:
        self._session = session
        self._clock = clock
        self._profile_directory: str | None = None

    def _directory(self) -> str:
        if self._profile_directory is None:
            result = self._session.shell(
                f"find /sdcard/Android/data/{_PACKAGE}/files -maxdepth 1 "
                "-type d -name 'NakamaLocal_*' | head -n 1"
            ).strip()
            if not _SAFE_PROFILE_PATH.fullmatch(result):
                raise FileNotFoundError("Draft Showdown local profile cache was not found")
            self._profile_directory = result
        return self._profile_directory

    def _profile(self, name: str) -> dict[str, Any]:
        if name not in _PROFILE_NAMES:
            raise ValueError(f"unsupported profile name: {name}")
        encoded = self._session.shell(f"cat '{self._directory()}/{name}.data'").strip()
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        result = json.loads(decoded)
        if not isinstance(result, dict):
            raise ValueError(f"{name} is not a JSON object")
        return result

    def read(self) -> AccountSnapshot:
        levels_data = self._profile("CardLevelsProfileData")
        mastery_data = self._profile("UnitMasteryProfileData")
        resource_data = self._profile("ResourcesProfileData")
        match_data = self._profile("MatchStatsProfileData")
        shop_data = self._profile("ShopProfileData")

        levels = {
            name: _integer(item.get("Amount"), 1)
            for item in levels_data.get("ul", ())
            if isinstance(item, dict)
            and (name := _unit_name(item.get("UnitType"))) is not None
        }
        mastery = {
            name: _integer(item.get("Amount"))
            for item in mastery_data.get("um", ())
            if isinstance(item, dict)
            and (name := _unit_name(item.get("UnitType"))) is not None
        }
        raw_resources = resource_data.get("rpr", {})
        resources = {
            "coins": _integer(raw_resources.get("Coin")),
            "trophies": _integer(raw_resources.get("Trophy")),
            "gems": _integer(raw_resources.get("Gem")),
            "mastery_currency": _integer(raw_resources.get("Chip")),
        }
        unit_stats: dict[str, dict[str, int]] = {}
        for raw_name, raw_stats in match_data.get("mscs", {}).items():
            name = _unit_name(raw_name)
            if name is None or not isinstance(raw_stats, dict):
                continue
            unit_stats[name] = {
                "available": _integer(raw_stats.get("mscsa")),
                "uses": _integer(raw_stats.get("mscsu")),
                "wins": _integer(raw_stats.get("mscsw")),
            }
        return AccountSnapshot(
            levels=levels,
            mastery_points=mastery,
            resources=resources,
            matches=_integer(match_data.get("mspm")),
            wins=_integer(match_data.get("msw")),
            losses=_integer(match_data.get("msl")),
            unit_stats=unit_stats,
            shop=shop_data,
            read_at_monotonic=float(self._clock()),
        )
