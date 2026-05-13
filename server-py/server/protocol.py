"""Wire protocol enums + payload dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HandPhase(str, Enum):
    PRE_DICE = "PRE_DICE"
    DEALING = "DEALING"
    FLOWER_RESOLUTION = "FLOWER_RESOLUTION"
    PLAYING = "PLAYING"
    SETTLEMENT = "SETTLEMENT"


class ClientEvent(str, Enum):
    ROLL_DICE = "roll_dice"
    DRAW_FRONT = "draw_front"
    DRAW_BACK = "draw_back"
    DISCARD = "discard"
    DECLARE_FLOWER = "declare_flower"
    CLAIM = "claim"
    DECLARE_CONCEALED_GANG = "declare_concealed_gang"
    DECLARE_ADDED_GANG = "declare_added_gang"
    DECLARE_SELF_HU = "declare_self_hu"
    UNDO = "undo"
    NEXT_HAND = "next_hand"
    CO_HU_RESPONSE = "co_hu_response"
    ROBBING_KONG_PASS_EVT = "robbing_kong_pass"


class ServerEvent(str, Enum):
    STATE_UPDATE = "state_update"
    DICE_ROLLED = "dice_rolled"
    DEALING_STEP = "dealing_step"
    HAND_SETTLEMENT = "hand_settlement"
    LOBBY_UPDATE = "lobby_update"
    START_GAME = "start_game"


class AvailableAction(str, Enum):
    """Server-computed action eligibility for a player. Drives the action bar."""
    ROLL_DICE = "roll_dice"
    DRAW_FRONT = "draw_front"
    DRAW_BACK = "draw_back"
    DISCARD = "discard"
    DECLARE_FLOWER = "declare_flower"
    CHI = "chi"
    PENG = "peng"
    GANG_OPEN = "gang_open"
    DECLARE_CONCEALED_GANG = "declare_concealed_gang"
    DECLARE_ADDED_GANG = "declare_added_gang"
    HU = "hu"
    UNDO = "undo"
    NEXT_HAND = "next_hand"
    CO_HU_PASS = "co_hu_pass"
    ROBBING_KONG_PASS = "robbing_kong_pass"


@dataclass
class WallPosition:
    """Physical position of a tile in the perimeter wall."""
    seat: int      # 0..3
    stack: int     # 0..17 (left-to-right from that seat's view)
    layer: int     # 0=top, 1=bottom


@dataclass
class DiceResult:
    d1: int
    d2: int
    d3: int
    sum: int
    break_seat: int
    break_offset: int
