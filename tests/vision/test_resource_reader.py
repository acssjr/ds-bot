from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from src.state.game_state import ScreenState
from src.vision.resource_reader import ResourceReader


class FieldEngine:
    def __init__(self, readings: list[tuple[str, float]]) -> None:
        self.readings = iter(readings)
        self.calls = 0

    def __call__(self, _image: np.ndarray, **_kwargs: object) -> object:
        self.calls += 1
        text, score = next(self.readings)
        return SimpleNamespace(txts=(text,), scores=(score,))


def test_home_reads_fixed_fields_and_throttles_ocr() -> None:
    engine = FieldEngine(
        [
            ("140/150", 0.99),
            ("125", 0.98),
            ("3578", 1.0),
            ("26", 0.97),
            ("489", 0.99),
            ("6", 0.99),
        ]
    )
    times = iter([10.0, 11.0])
    reader = ResourceReader(engine_factory=lambda: engine, clock=times.__next__)
    frame = np.zeros((1280, 720, 3), dtype=np.uint8)

    first = reader.analyze(frame, ScreenState.HOME)
    second = reader.analyze(frame, ScreenState.HOME)

    assert first["resource_ocr_status"] == "fresh"
    assert first["resources"] == {
        "energy_current": 140,
        "energy_capacity": 150,
        "gems": 125,
        "coins": 3578,
        "mastery_currency": 26,
        "trophies": 489,
        "player_level": 6,
        "resource_confidence": 0.97,
    }
    assert second["resource_ocr_status"] == "cached"
    assert second["resources"] == first["resources"]
    assert engine.calls == 6


class CollectionEngine:
    def __init__(self) -> None:
        self.field_readings = iter(
            [("140/150", 1.0), ("100", 1.0), ("5478", 1.0), ("26", 1.0)]
        )
        self.calls = 0

    def __call__(self, _image: np.ndarray, **kwargs: object) -> object:
        self.calls += 1
        if kwargs.get("use_det") is False:
            text, score = next(self.field_readings)
            return SimpleNamespace(txts=(text,), scores=(score,))
        return SimpleNamespace(
            boxes=np.array(
                [
                    [[500, 540], [585, 540], [585, 588], [500, 588]],
                    [[35, 789], [163, 789], [163, 822], [35, 822]],
                    [[18, 832], [52, 832], [52, 869], [18, 869]],
                    [[220, 786], [325, 786], [325, 827], [220, 827]],
                    [[192, 831], [226, 831], [226, 870], [192, 870]],
                ],
                dtype=float,
            ),
            txts=("9/25", "Cavaleiro", "3", "Cupido", "4"),
            scores=(1.0, 1.0, 1.0, 1.0, 1.0),
        )


def test_collection_maps_visible_unit_levels_on_entry() -> None:
    engine = CollectionEngine()
    reader = ResourceReader(engine_factory=lambda: engine, clock=lambda: 10.0)

    result = reader.analyze(np.zeros((1280, 720, 3), dtype=np.uint8), ScreenState.COLLECTION_MENU)

    resources = result["resources"]
    assert resources["collection_unlocked"] == 9
    assert resources["collection_total"] == 25
    assert resources["units"] == (
        {"name": "Cavaleiro", "level": 3, "confidence": 1.0},
        {"name": "Cupido", "level": 4, "confidence": 1.0},
    )
    assert engine.calls == 5


class LeagueEngine(CollectionEngine):
    def __call__(self, image: np.ndarray, **kwargs: object) -> object:
        if kwargs.get("use_det") is False:
            return super().__call__(image, **kwargs)
        self.calls += 1
        return SimpleNamespace(
            boxes=np.array(
                [
                    [[250, 175], [470, 175], [470, 205], [250, 205]],
                    [[250, 220], [470, 220], [470, 260], [250, 260]],
                    [[40, 700], [85, 700], [85, 740], [40, 740]],
                    [[170, 700], [330, 700], [330, 740], [170, 740]],
                    [[600, 700], [665, 700], [665, 740], [600, 740]],
                ],
                dtype=float,
            ),
            txts=("Termina em: 5d 03h", "LIGA BRONZE", "4", "EuPiroca", "108"),
            scores=(1.0,) * 5,
        )


def test_league_maps_player_row_and_season() -> None:
    engine = LeagueEngine()
    reader = ResourceReader(engine_factory=lambda: engine, clock=lambda: 10.0)

    result = reader.analyze(np.zeros((1280, 720, 3), dtype=np.uint8), ScreenState.LEAGUE_MENU)

    resources = result["resources"]
    assert resources["league"] == "Bronze"
    assert resources["league_ends"] == "5d 03h"
    assert resources["league_rank"] == 4
    assert resources["league_points"] == 108
