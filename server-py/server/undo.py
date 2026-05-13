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
        "dice_result": copy.deepcopy(hand.dice_result),
        "pending_flowers": copy.deepcopy(hand.pending_flowers),
        "wall_rotation_offset": hand.wall_rotation_offset,
        "co_hu_joined": list(hand.co_hu_joined),
        "co_hu_remaining": list(hand.co_hu_remaining),
        "co_hu_declined": list(hand.co_hu_declined),
        "co_hu_active": hand.co_hu_active,
        "robbing_kong_pending": list(hand.robbing_kong_pending),
        "event_log": copy.deepcopy(hand.event_log),
    })


def restore_snapshot(hand, snap: HandSnapshot) -> None:
    hand.game = snap.payload["game"]
    hand.phase = snap.payload["phase"]
    hand.must_draw_back = snap.payload["must_draw_back"]
    hand.dice_result = snap.payload["dice_result"]
    hand.pending_flowers = snap.payload["pending_flowers"]
    hand.wall_rotation_offset = snap.payload["wall_rotation_offset"]
    hand.co_hu_joined = list(snap.payload.get("co_hu_joined", []))
    hand.co_hu_remaining = list(snap.payload.get("co_hu_remaining", []))
    hand.co_hu_declined = list(snap.payload.get("co_hu_declined", []))
    hand.co_hu_active = snap.payload.get("co_hu_active", False)
    hand.robbing_kong_pending = list(snap.payload.get("robbing_kong_pending", []))
    hand.event_log = list(snap.payload.get("event_log", []))
