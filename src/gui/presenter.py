from __future__ import annotations

import math
from dataclasses import dataclass

from src.core.events import EventKind, RuntimeEvent
from src.core.lifecycle import RuntimeStatus


@dataclass(frozen=True, slots=True)
class LifecyclePresentation:
    label: str
    color: str
    terminal: bool


_LIFECYCLE_PRESENTATIONS = {
    RuntimeStatus.STARTING: LifecyclePresentation("🟠 INICIANDO", "#E65100", False),
    RuntimeStatus.RUNNING: LifecyclePresentation("🟢 OBSERVANDO", "#2E7D32", False),
    RuntimeStatus.PAUSED: LifecyclePresentation("🟠 PAUSADO", "#E65100", False),
    RuntimeStatus.STOPPING: LifecyclePresentation("🟠 PARANDO", "#E65100", False),
    RuntimeStatus.STOPPED: LifecyclePresentation("🔴 PARADO", "#A91B0D", True),
    RuntimeStatus.FAILED: LifecyclePresentation("🔴 FALHA", "#A91B0D", True),
}


def format_runtime_event(event: RuntimeEvent) -> str | None:
    if event.kind is not EventKind.OBSERVATION:
        return None
    try:
        confidence = float(event.payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if not math.isfinite(confidence):
        confidence = 0.0
    confidence = min(1.0, max(0.0, confidence))
    return (
        f"Tela: {event.payload.get('screen', 'UNKNOWN')} | "
        f"Confiança: {confidence:.0%} | "
        f"Elemento: {event.payload.get('sub_element') or '-'} | "
        f"Frame: {event.payload.get('frame_id', '-')}"
    )


def present_lifecycle(event: RuntimeEvent) -> LifecyclePresentation | None:
    if event.kind is not EventKind.LIFECYCLE:
        return None
    try:
        status = RuntimeStatus(event.payload.get("status"))
    except (TypeError, ValueError):
        return None
    return _LIFECYCLE_PRESENTATIONS[status]


def format_runtime_error(event: RuntimeEvent) -> str | None:
    if event.kind is not EventKind.ERROR:
        return None
    error = str(event.payload.get("error") or "erro desconhecido")
    phase = event.payload.get("phase")
    return f"{phase}: {error}" if phase else error
