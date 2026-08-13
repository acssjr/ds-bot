from src.core.events import EventKind, RuntimeEvent
from src.gui.presenter import (
    format_runtime_error,
    format_runtime_event,
    present_lifecycle,
)


def test_observation_event_is_formatted_without_tk_dependency() -> None:
    event = RuntimeEvent(
        EventKind.OBSERVATION,
        1.0,
        {
            "frame_id": 7,
            "screen": "HOME",
            "confidence": 0.923,
            "sub_element": "battle",
        },
    )

    assert (
        format_runtime_event(event)
        == "Tela: HOME | Confiança: 92% | Elemento: battle | Frame: 7"
    )


def test_observation_defaults_are_explicit() -> None:
    event = RuntimeEvent(EventKind.OBSERVATION, 1.0, {})

    assert (
        format_runtime_event(event)
        == "Tela: UNKNOWN | Confiança: 0% | Elemento: - | Frame: -"
    )


def test_invalid_observation_confidence_does_not_break_gui_polling() -> None:
    event = RuntimeEvent(
        EventKind.OBSERVATION,
        1.0,
        {"confidence": "indisponível"},
    )

    assert (
        format_runtime_event(event)
        == "Tela: UNKNOWN | Confiança: 0% | Elemento: - | Frame: -"
    )


def test_non_observation_event_has_no_observation_text() -> None:
    event = RuntimeEvent(EventKind.FRAME, 1.0, {"frame_id": 7})

    assert format_runtime_event(event) is None


def test_running_lifecycle_is_presented_as_observation() -> None:
    event = RuntimeEvent(EventKind.LIFECYCLE, 1.0, {"status": "running"})

    presentation = present_lifecycle(event)

    assert presentation is not None
    assert presentation.label == "🟢 OBSERVANDO"
    assert presentation.color == "#2E7D32"
    assert presentation.terminal is False


def test_failed_lifecycle_is_terminal() -> None:
    event = RuntimeEvent(EventKind.LIFECYCLE, 1.0, {"status": "failed"})

    presentation = present_lifecycle(event)

    assert presentation is not None
    assert presentation.label == "🔴 FALHA"
    assert presentation.terminal is True


def test_error_event_is_formatted_once_by_caller_key() -> None:
    event = RuntimeEvent(
        EventKind.ERROR,
        1.0,
        {"phase": "run", "error": "DeviceNotFound('emulador')"},
    )

    assert format_runtime_error(event) == "run: DeviceNotFound('emulador')"


def test_non_error_event_has_no_error_text() -> None:
    event = RuntimeEvent(EventKind.LIFECYCLE, 1.0, {"status": "stopped"})

    assert format_runtime_error(event) is None
