import pytest

from src.automation.main import build_parser


def test_live_executor_requires_explicit_device_and_confirmation() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--device", "127.0.0.1:21503"])


def test_live_executor_accepts_bounded_explicit_invocation() -> None:
    args = build_parser().parse_args(
        [
            "--device",
            "127.0.0.1:21503",
            "--confirm-live-input",
            "--max-minutes",
            "20",
        ]
    )

    assert args.device == "127.0.0.1:21503"
    assert args.confirm_live_input is True
    assert args.max_minutes == 20


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_live_executor_rejects_invalid_max_minutes(value: str) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--device", "A", "--confirm-live-input", "--max-minutes", value]
        )
