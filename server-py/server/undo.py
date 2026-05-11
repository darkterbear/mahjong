"""Snapshot stack for in-hand undo. Uses copy.deepcopy."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


@dataclass
class HandSnapshot:
    """Frozen state of a Hand at a point in time."""
    payload: dict[str, Any]


def take_snapshot(hand) -> HandSnapshot:
    return HandSnapshot(payload={
        "game": copy.deepcopy(hand.game),
        "phase": hand.phase,
        "must_draw_back": hand.must_draw_back,
        "flower_resolution_seat": hand.flower_resolution_seat,
        "dice_result": copy.deepcopy(hand.dice_result),
        "pending_flowers": copy.deepcopy(hand.pending_flowers),
    })


def restore_snapshot(hand, snap: HandSnapshot) -> None:
    hand.game = snap.payload["game"]
    hand.phase = snap.payload["phase"]
    hand.must_draw_back = snap.payload["must_draw_back"]
    hand.flower_resolution_seat = snap.payload["flower_resolution_seat"]
    hand.dice_result = snap.payload["dice_result"]
    hand.pending_flowers = snap.payload["pending_flowers"]
