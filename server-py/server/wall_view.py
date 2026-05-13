"""Translate flat wall indices to/from physical (seat, stack, layer) positions."""
from __future__ import annotations

from server.protocol import WallPosition

NUM_SEATS = 4
STACKS_PER_SEAT = 18
LAYERS_PER_STACK = 2
TILES_PER_SEAT = STACKS_PER_SEAT * LAYERS_PER_STACK  # 36
TOTAL_WALL_TILES = NUM_SEATS * TILES_PER_SEAT        # 144


def flat_to_position(flat: int) -> WallPosition:
    if flat < 0 or flat >= TOTAL_WALL_TILES:
        raise ValueError(f"flat index {flat} out of range [0, {TOTAL_WALL_TILES})")
    seat = flat // TILES_PER_SEAT
    local = flat % TILES_PER_SEAT
    stack = local // LAYERS_PER_STACK
    layer = local % LAYERS_PER_STACK
    return WallPosition(seat=seat, stack=stack, layer=layer)


def position_to_flat(pos: WallPosition) -> int:
    return (
        pos.seat * TILES_PER_SEAT
        + pos.stack * LAYERS_PER_STACK
        + pos.layer
    )
