import base64
import json

from src.device.profile_reader import AdbProfileReader


class FakeSession:
    def __init__(self, profiles):
        self.profiles = profiles

    def shell(self, command: str) -> str:
        if command.startswith("find "):
            return "/sdcard/Android/data/com.QuestLab.DraftWar/files/NakamaLocal_test\n"
        name = command.rsplit("/", 1)[-1].removesuffix(".data'")
        payload = json.dumps(self.profiles[name]).encode()
        return base64.b64encode(payload).decode()


def test_reads_exact_account_progression_and_performance_from_adb_cache() -> None:
    reader = AdbProfileReader(
        FakeSession(
            {
                "CardLevelsProfileData": {
                    "ul": [{"UnitType": "Engineer1", "Amount": 5}]
                },
                "UnitMasteryProfileData": {
                    "um": [{"UnitType": "Engineer1", "Amount": 283}]
                },
                "ResourcesProfileData": {
                    "rpr": {"Coin": 1178, "Trophy": 540, "Gem": 175, "Chip": 22}
                },
                "MatchStatsProfileData": {
                    "mspm": 30,
                    "msw": 27,
                    "msl": 3,
                    "mscs": {
                        "Engineer1": {"mscsa": 18, "mscsu": 18, "mscsw": 15}
                    },
                },
                "ShopProfileData": {"shaw": {"StoreCoin": 1}},
            }
        ),
        clock=lambda: 10.0,
    )

    snapshot = reader.read()

    assert snapshot.level_for("Engenheiro") == 5
    assert snapshot.mastery_for("Engineer") == 283
    assert snapshot.resources == {
        "coins": 1178,
        "trophies": 540,
        "gems": 175,
        "mastery_currency": 22,
    }
    assert snapshot.win_rate == 0.9
    assert snapshot.resource_payload()["units"][0] == {
        "name": "Engenheiro",
        "level": 5,
        "mastery_points": 283,
        "uses": 18,
        "wins": 15,
    }
