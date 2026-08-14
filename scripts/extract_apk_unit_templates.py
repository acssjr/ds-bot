"""Extract a minimal, reproducible unit-template set from an installed game APK.

This is a development tool, not a runtime dependency.  Run it with UnityPy in
an isolated tool environment; the application only consumes the generated PNGs.
"""

from __future__ import annotations

import argparse
import tempfile
import zipfile
from pathlib import Path

import UnityPy


SPRITES = {
    "knight_enemy_helmet.png": "Sprite Knight Helmet Flag Enemy",
    "cupid_enemy.png": "Sprite UnitThumbnail Cupid Opponent",
    "goose_enemy.png": "Sprite UnitThumbnail Goose Opponent",
    "tnt_enemy_body.png": "Sprite TNT Body Enemy",
    "snail_enemy.png": "Sprite UnitThumbnail Snail Opponent",
    "assassin_enemy.png": "Sprite UnitThumbnail Assassin Opponent",
    "kingclops_enemy.png": "Sprite UnitThumbnail Kingclops Opponent",
    "engineer_enemy.png": "Sprite UnitThumbnail Engineer Opponent",
    "engineer_enemy_head.png": "Sprite Engineer Head Opponent",
    "engineer_enemy_bag2.png": "Sprite Engineer2 Bag",
    "engineer_enemy_bag3.png": "Sprite Engineer3 Bag",
}


def extract(apk: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="draft-showdown-unity-") as temporary:
        bundle = Path(temporary) / "data.unity3d"
        with zipfile.ZipFile(apk) as archive:
            with archive.open("assets/bin/Data/data.unity3d") as source:
                bundle.write_bytes(source.read())

        environment = UnityPy.load(str(bundle))
        remaining = dict(SPRITES)
        for unity_object in environment.objects:
            if unity_object.type.name != "Sprite":
                continue
            sprite = unity_object.read()
            for filename, expected_name in tuple(remaining.items()):
                if sprite.m_Name == expected_name:
                    sprite.image.save(output / filename)
                    remaining.pop(filename)
        if remaining:
            missing = ", ".join(sorted(remaining.values()))
            raise RuntimeError(f"sprites not found in this APK: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    if not arguments.apk.is_file():
        parser.error(f"APK does not exist: {arguments.apk}")
    extract(arguments.apk.resolve(), arguments.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
