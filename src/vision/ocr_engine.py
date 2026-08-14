from __future__ import annotations

from threading import Lock
from typing import Any


_engine: Any | None = None
_engine_lock = Lock()


def shared_rapidocr() -> Any:
    """Create one lazy OCR engine for the single visual worker."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
    return _engine
