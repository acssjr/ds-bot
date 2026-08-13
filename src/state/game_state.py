import time
from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

class ScreenState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HOME = "HOME"
    WAIT_MATCHMAKING = "WAIT_MATCHMAKING"
    DRAFT_SCREEN = "DRAFT_SCREEN"
    POSITION_UNITS = "POSITION_UNITS"
    COMBAT = "COMBAT"
    ROUND_RESULT = "ROUND_RESULT"
    VICTORY_SUMMARY = "VICTORY_SUMMARY"
    DOUBLE_BITS = "DOUBLE_BITS"
    MASTERY_BOOST = "MASTERY_BOOST"
    BIT_PACK_OPENING = "BIT_PACK_OPENING"
    NEW_UNIT_UNLOCKED = "NEW_UNIT_UNLOCKED"
    WATCHING_AD = "WATCHING_AD"
    COLLECTION_MENU = "COLLECTION_MENU"

class CardRole(str, Enum):
    TANK = "Tank"
    RANGED_DPS = "Ranged DPS"
    UTILITY = "Utility"
    ASSASSIN = "Assassin"
    TANKY_DPS = "Tanky DPS"
    UNKNOWN = "Unknown"

class CardChoice(BaseModel):
    slot_index: int = Field(ge=0, le=2)
    card_id: str = "unknown"
    name: str = "Unknown Card"
    role: CardRole = CardRole.UNKNOWN
    rarity: str = "Common"
    level: int = 1
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class UnitOnBoard(BaseModel):
    unit_id: str
    is_ally: bool
    grid_x: int
    grid_y: int
    health_percent: float = Field(default=1.0, ge=0.0, le=1.0)
    bounding_box: Tuple[int, int, int, int]

class SessionStats(BaseModel):
    total_battles: int = 0
    wins: int = 0
    losses: int = 0
    ads_watched: int = 0
    bits_collected: int = 0
    start_time: float = Field(default_factory=time.time)

    @property
    def win_rate(self) -> float:
        if self.total_battles == 0:
            return 0.0
        return (self.wins / self.total_battles) * 100.0

    @property
    def uptime_str(self) -> str:
        elapsed = int(time.time() - self.start_time)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

class GameState(BaseModel):
    screen: ScreenState = ScreenState.UNKNOWN
    sub_element: Optional[str] = None
    round_number: int = 1
    draw_number: int = 1
    player_lives: int = 4
    opponent_lives: int = 4
    available_choices: List[CardChoice] = []
    selected_deck: List[str] = []
    player_board: List[UnitOnBoard] = []
    opponent_board: List[UnitOnBoard] = []
    gold: int = 0
    gems: int = 0
    confidence: float = 0.0
    timestamp: float = 0.0
    stats: SessionStats = Field(default_factory=SessionStats)
