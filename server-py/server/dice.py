"""Dice roll + break-point computation + wall rotation."""
from __future__ import annotations

import random
from typing import TypeVar

from server.protocol import DiceResult
from server.wall_view import STACKS_PER_SEAT, TILES_PER_SEAT

T = TypeVar("T")


def roll_dice(rng: random.Random, dealer_seat: int = 0) -> DiceResult:
    """Roll 3d6 and compute the resulting break point.

    Convention: break_seat = (dealer_seat + dice_sum - 1) % 4 — counts dealer
    as 1, going counterclockwise. break_offset is the dice sum, indicating the
    stack offset from the right edge of break_seat's wall.
    """
    d1 = rng.randint(1, 6)
    d2 = rng.randint(1, 6)
    d3 = rng.randint(1, 6)
    s = d1 + d2 + d3
    break_seat = (dealer_seat + s - 1) % 4
    return DiceResult(
        d1=d1, d2=d2, d3=d3, sum=s,
        break_seat=break_seat, break_offset=s,
    )


def compute_break_position(dealer_seat: int, dice_sum: int) -> tuple[int, int]:
    """Return (break_seat, break_stack_index) per the standard rule.

    Counting the dealer as 1 and walking counterclockwise, the dice sum picks
    which player's wall to break. Then from the right edge of that player's
    wall (their POV), count `dice_sum` stacks clockwise; the break lands on
    the counted stack.
    """
    seat = (dealer_seat + dice_sum - 1) % 4
    # Counting from the right edge (stack index STACKS_PER_SEAT - 1), going
    # clockwise (decreasing stack index), the k-th stack counted is index
    # STACKS_PER_SEAT - k. Clamp to keep within the wall.
    stack = STACKS_PER_SEAT - dice_sum
    stack = max(0, min(STACKS_PER_SEAT - 1, stack))
    return seat, stack


def rotate_wall_for_break(tiles: list[T], break_seat: int, break_stack: int) -> list[T]:
    """Rotate tiles so that (break_seat, break_stack, layer=0) lands at index 0.

    Subterfuge's Wall.draw() always pops from index 0 forward, so we pre-rotate
    to align the conceptual break point with index 0.
    """
    flat_break = break_seat * TILES_PER_SEAT + break_stack * 2
    return tiles[flat_break:] + tiles[:flat_break]
