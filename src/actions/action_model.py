from enum import Enum, auto
from typing import Optional, Tuple
from pydantic import BaseModel

class ActionType(str, Enum):
    TAP = "TAP"
    SWIPE = "SWIPE"
    DRAG_AND_DROP = "DRAG_AND_DROP"
    WAIT = "WAIT"

class Action(BaseModel):
    action_type: ActionType
    normalized_start: Tuple[float, float]  # (x, y) em escala 0.0 - 1.0
    normalized_end: Optional[Tuple[float, float]] = None  # Para Drag/Swipe
    duration_ms: int = 50
    post_delay_ms: int = 200
    metadata: str = ""
