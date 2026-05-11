"""Room registry, Player records, lobby flow."""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from typing import Optional, ClassVar

from server.session import Session


@dataclass
class Player:
    player_id: str       # session id from cookie/socket auth
    username: str
    sid: Optional[str] = None  # current socket sid (None if disconnected)


class Room:
    _registry: ClassVar[dict[str, "Room"]] = {}

    def __init__(self, code: str) -> None:
        self.code: str = code
        self.players: list[Player] = []
        self.leader: Optional[Player] = None
        self.session: Optional[Session] = None

    # ---- registry ----------------------------------------------------------

    @classmethod
    def create(cls) -> "Room":
        code = cls._generate_unique_code()
        room = cls(code)
        cls._registry[code] = room
        return room

    @classmethod
    def get(cls, code: str) -> Optional["Room"]:
        return cls._registry.get(code)

    @classmethod
    def reset_registry(cls) -> None:
        cls._registry.clear()

    @staticmethod
    def _generate_unique_code() -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase, k=4))
            if code not in Room._registry:
                return code

    # ---- lobby ops ---------------------------------------------------------

    def add_player(self, p: Player) -> None:
        if self.session is not None:
            raise RuntimeError("cannot join: session in progress")
        if len(self.players) >= 4:
            raise ValueError("room full")
        self.players.append(p)
        if self.leader is None:
            self.leader = p

    def remove_player(self, player_id: str) -> None:
        before = len(self.players)
        self.players = [p for p in self.players if p.player_id != player_id]
        if not self.players:
            del Room._registry[self.code]
            return
        if self.leader and self.leader.player_id == player_id:
            self.leader = self.players[0]

    def start_session(self, seed: Optional[int] = None) -> Session:
        if len(self.players) != 4:
            raise RuntimeError("session requires 4 players")
        self.session = Session([p.player_id for p in self.players], seed=seed)
        return self.session

    def player_by_seat(self, seat: int) -> Player:
        if not self.session:
            raise RuntimeError("no session")
        pid = self.session.seats[seat]
        return next(p for p in self.players if p.player_id == pid)
