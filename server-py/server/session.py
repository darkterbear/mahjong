"""Multi-hand session state: seats, dealer rotation, scores."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from server.hand import Hand


@dataclass
class HandResult:
    winner_seat: Optional[int]   # None for draw
    is_self_draw: bool
    is_draw: bool                # wall exhaustion
    payments: list[int]          # length 4
    breakdown: dict[str, int]
    total: int
    winning_tile: Optional[int] = None


class Session:
    """Multi-hand session for a single room."""

    def __init__(self, player_ids: list[str], seed: Optional[int] = None) -> None:
        if len(player_ids) != 4:
            raise ValueError("Session requires exactly 4 player IDs")
        rng = random.Random(seed)
        self.seats: list[str] = list(player_ids)
        rng.shuffle(self.seats)

        self.dealer_seat: int = 0
        self.dealer_streak: int = 0
        self.round_wind_index: int = 0
        self.dealer_rotations_this_round: int = 0
        self.cumulative_scores: list[int] = [0, 0, 0, 0]
        self.hand_history: list[HandResult] = []
        self.current_hand: Optional[Hand] = None
        self._rng = rng

    def start_new_hand(self) -> Hand:
        seed = self._rng.randint(0, 2**31 - 1)
        self.current_hand = Hand(
            dealer_seat=self.dealer_seat,
            round_wind_index=self.round_wind_index,
            dealer_streak=self.dealer_streak,
            seed=seed,
        )
        return self.current_hand

    def record_settlement(self, result: HandResult) -> None:
        for i in range(4):
            self.cumulative_scores[i] += result.payments[i]
        self.hand_history.append(result)

        dealer_kept = (
            result.is_draw
            or (result.winner_seat is not None and result.winner_seat == self.dealer_seat)
        )
        if dealer_kept:
            self.dealer_streak += 1
        else:
            self.dealer_seat = (self.dealer_seat + 1) % 4
            self.dealer_streak = 0
            self.dealer_rotations_this_round += 1
            if self.dealer_rotations_this_round == 4:
                self.round_wind_index = (self.round_wind_index + 1) % 4
                self.dealer_rotations_this_round = 0

        self.current_hand = None

    def next_hand_dealer_seat(self) -> int:
        """Seat that will be dealer for the *next* hand (post-settlement)."""
        return self.dealer_seat
