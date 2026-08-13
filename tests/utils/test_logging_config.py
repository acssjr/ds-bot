from __future__ import annotations

from pathlib import Path

from src.utils import logging_config


class FakeLogger:
    def __init__(self) -> None:
        self.removed = False
        self.add_calls: list[tuple[object, dict[str, object]]] = []

    def remove(self) -> None:
        self.removed = True

    def add(self, sink: object, **kwargs: object) -> int:
        self.add_calls.append((sink, kwargs))
        return len(self.add_calls)


def test_cli_logging_uses_only_synchronous_bounded_by_io_sinks(monkeypatch) -> None:
    fake = FakeLogger()
    monkeypatch.setattr(logging_config, "logger", fake)

    configured = logging_config.setup_logger("INFO")

    assert configured is fake
    assert fake.removed is True
    assert len(fake.add_calls) == 2
    assert all(options["enqueue"] is False for _sink, options in fake.add_calls)
    _console, file_sink = fake.add_calls
    assert file_sink[1]["rotation"] == "10 MB"
    assert file_sink[1]["retention"] == "7 days"


def test_logging_source_cannot_enable_loguru_unbounded_queue() -> None:
    source = Path("src/utils/logging_config.py").read_text(encoding="utf-8")

    assert "enqueue=True" not in source.replace(" ", "")
