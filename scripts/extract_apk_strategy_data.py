from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


UNIT_ORDER = (
    "Knight", "Cupid", "Goose", "TNT", "Snail", "Assassin", "Splime",
    "Kingclops", "Waster", "Beetank", "Mole", "Sniper", "Wizard",
    "Turtle", "Spartan", "Parasite", "Cowboy", "ManEater", "Agent",
    "Villain", "Goblin", "Totem", "Engineer", "Spider", "Dragon",
)

PREFAB_NAMES = {
    "Snail": "Snail1",
    "Splime": "Splime1",
    "ManEater": "Plant",
    "Villain": "Vilain",
}

BEHAVIOUR_FIELDS = (
    "teleportStartDelayMin",
    "teleportStartDelayMax",
    "teleportWaitDelay",
    "firstSpawnDelay",
    "spawnDelay",
    "spawnDelayRandom",
    "switchDelay",
    "firstSwitchDelay",
    "chance",
)


def _read_csv(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def _number(value: str) -> int | float:
    result = float(value)
    return int(result) if result.is_integer() else result


def _formula_base(value: str) -> int | float:
    match = re.match(r"\s*([\d.]+)\s*\*", value)
    if match is None:
        raise ValueError(f"unsupported stat formula: {value!r}")
    return _number(match.group(1))


def _formula_level_multiplier(value: str) -> int | float:
    match = re.search(r"pow\(([\d.]+),", value)
    if match is None:
        raise ValueError(f"unsupported stat formula: {value!r}")
    return _number(match.group(1))


def _asset_index(assets: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for folder in ("AnimatorController", "AnimatorOverrideController", "AnimationClip"):
        for meta in (assets / folder).glob("*.meta"):
            match = re.search(r"^guid: (\w+)", meta.read_text(encoding="utf-8"), re.M)
            if match is not None:
                index[match.group(1)] = meta.with_suffix("")
    return index


def _main_component(prefab: str) -> str:
    return next(
        block
        for block in prefab.split("--- !u!114")
        if "\n  maxSpeed:" in block and "\n  health:" in block
    )


def _scalar(text: str, field: str) -> int | float | None:
    match = re.search(rf"^  {re.escape(field)}: ([\d.Ee+-]+)$", text, re.M)
    return _number(match.group(1)) if match else None


def _attack_animation(
    assets: Path,
    prefab: str,
    main: str,
    index: dict[str, Path],
) -> dict[str, object] | None:
    animator_id = re.search(r"^  animator: \{fileID: (\d+)\}", main, re.M)
    if animator_id is None:
        return None
    animator = re.search(
        rf"^--- !u!95 &{animator_id.group(1)}\nAnimator:\n(.*?)(?=^--- !u!|\Z)",
        prefab,
        re.M | re.S,
    )
    if animator is None:
        return None
    controller_ref = re.search(
        r"m_Controller: \{fileID: (?:9100000|22100000), guid: (\w+)",
        animator.group(1),
    )
    asset = index.get(controller_ref.group(1)) if controller_ref else None
    if asset is None:
        return None

    overrides: dict[str, str] = {}
    controller = asset
    if asset.parent.name == "AnimatorOverrideController":
        override_text = asset.read_text(encoding="utf-8")
        base_ref = re.search(
            r"m_Controller: \{fileID: 9100000, guid: (\w+)", override_text
        )
        controller = index.get(base_ref.group(1)) if base_ref else None
        overrides = dict(
            re.findall(
                r"m_OriginalClip: \{fileID: 7400000, guid: (\w+).*?\n"
                r"    m_OverrideClip: \{fileID: 7400000, guid: (\w+)",
                override_text,
            )
        )
    if controller is None:
        return None

    states = re.split(
        r"(?=^--- !u!1102)", controller.read_text(encoding="utf-8"), flags=re.M
    )
    state = next(
        (item for item in states if re.search(r"^  m_Name: Attack$", item, re.M)),
        None,
    )
    if state is None:
        return None
    motion = re.search(r"m_Motion: \{fileID: 7400000, guid: (\w+)", state)
    if motion is None:
        return None
    clip = index.get(overrides.get(motion.group(1), motion.group(1)))
    if clip is None:
        return None
    clip_text = clip.read_text(encoding="utf-8")
    stop_time = re.search(r"^    m_StopTime: ([\d.Ee+-]+)", clip_text, re.M)
    state_speed = re.search(r"^  m_Speed: ([\d.Ee+-]+)", state, re.M)
    if stop_time is None:
        return None
    speed = float(state_speed.group(1)) if state_speed else 1.0
    events = tuple(
        {"time_seconds": _number(time), "name": name}
        for time, name in re.findall(
            r"- time: ([\d.Ee+-]+)\n    functionName: (\w+)", clip_text
        )
    )
    return {
        "clip": clip.stem,
        "cycle_seconds": round(float(stop_time.group(1)) / speed, 6),
        "events": events,
    }


def extract(assets: Path, *, apk_version: str) -> dict[str, object]:
    setup = assets / "Resources" / "setups"
    upgrade_rows = _read_csv(setup / "UnitUpgradeSetup.txt")
    upgrades = {row[0].removesuffix("1"): row for row in upgrade_rows[1:] if row}

    pool_rows = _read_csv(setup / "DraftPool.txt")
    pools: dict[str, dict[str, int]] = {name: {} for name in UNIT_ORDER}
    for row in pool_rows[1:]:
        name = row[0].removesuffix("1")
        phase = "early" if row[1].endswith(" Early") else "late"
        match = re.search(r"(?: x(\d+))?$", row[2])
        pools[name][phase] = int(match.group(1) or 1)

    index = _asset_index(assets)
    units: dict[str, object] = {}
    for name in UNIT_ORDER:
        prefab_name = PREFAB_NAMES.get(name, name)
        prefab_text = (assets / "GameObject" / f"Unit {prefab_name}.prefab").read_text(
            encoding="utf-8"
        )
        main = _main_component(prefab_text)
        row = upgrades[name]
        behaviour: dict[str, object] = {}
        for field in BEHAVIOUR_FIELDS:
            value = _scalar(prefab_text, field)
            if value is not None:
                behaviour[field] = value
        units[name] = {
            "health": _formula_base(row[1]),
            "damage": _formula_base(row[2]),
            "display_damage": _formula_base(row[6]),
            "stat_multiplier_per_level": _formula_level_multiplier(row[1]),
            "first_upgrade_cost": int(row[3]),
            "upgrade_cost_multiplier_per_level": _number(row[4]),
            "max_level": int(row[5]),
            "spawn_early": pools[name]["early"],
            "spawn_late": pools[name]["late"],
            "move_speed": _scalar(main, "maxSpeed"),
            "acceleration": _scalar(main, "acceleration"),
            "attack_range": _scalar(main, "attackRange"),
            "stop_distance": _scalar(main, "stopDistanceFromTarget"),
            "attack_timing_jitter": _scalar(main, "attackSpeedRandomMultiplier"),
            "attack_animation": _attack_animation(assets, prefab_text, main, index),
            "behaviour": behaviour,
        }

    def matrix(name: str) -> dict[str, dict[str, int]]:
        rows = _read_csv(setup / name)
        columns = rows[0][1:]
        if tuple(columns) != UNIT_ORDER:
            raise ValueError(f"unexpected unit order in {name}")
        return {
            row[0]: {column: int(value) for column, value in zip(columns, row[1:])}
            for row in rows[1:]
        }

    count_rows = _read_csv(setup / "AiUnitCountSetup.txt")
    return {
        "schema_version": 1,
        "apk_version": apk_version,
        "sources": {
            "balance": "Resources/setups/UnitUpgradeSetup.txt",
            "draft_pool": "Resources/setups/DraftPool.txt",
            "unit_count": "Resources/setups/AiUnitCountSetup.txt",
            "synergy": "Resources/setups/DraftSynergySetup.txt",
            "counter_tendency": "Resources/setups/AiTendencySetup.txt",
            "movement_and_behaviour": "GameObject/Unit *.prefab",
            "attack_timing": "AnimatorController + AnimationClip",
        },
        "unit_order": UNIT_ORDER,
        "units": units,
        "unit_count_scores": {
            row[0]: tuple(int(value) for value in row[1:]) for row in count_rows[1:]
        },
        "synergy": matrix("DraftSynergySetup.txt"),
        "counter_tendency": matrix("AiTendencySetup.txt"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract auditable strategy facts from an AssetRipper export."
    )
    parser.add_argument("assets", type=Path, help="ExportedProject/Assets directory")
    parser.add_argument("output", type=Path)
    parser.add_argument("--apk-version", default="1.14.1")
    args = parser.parse_args()
    data = extract(args.assets.resolve(), apk_version=args.apk_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
