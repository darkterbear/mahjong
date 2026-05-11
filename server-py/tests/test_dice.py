import random

import pytest

from server.dice import roll_dice, compute_break_position, rotate_wall_for_break


def test_roll_dice_seeded() -> None:
    rng = random.Random(0)
    result = roll_dice(rng)
    assert 3 <= result.sum <= 18
    assert result.sum == result.d1 + result.d2 + result.d3
    assert 1 <= result.d1 <= 6
    assert 1 <= result.d2 <= 6
    assert 1 <= result.d3 <= 6


def test_roll_dice_records_break() -> None:
    rng = random.Random(0)
    # dealer at seat 0
    result = roll_dice(rng, dealer_seat=0)
    expected_seat = (0 + result.sum - 1) % 4
    assert result.break_seat == expected_seat
    assert result.break_offset == result.sum


def test_compute_break_position_simple() -> None:
    # dice_sum = 5, dealer = 0 → seat = (0+5-1) % 4 = 0; stack = 18-5 = 13.
    seat, stack = compute_break_position(dealer_seat=0, dice_sum=5)
    assert seat == 0
    assert stack == 13


def test_compute_break_position_wraps() -> None:
    # dealer = 2, dice_sum = 7 → break_seat = (2 + 6) % 4 = 0
    seat, stack = compute_break_position(dealer_seat=2, dice_sum=7)
    assert seat == 0


def test_rotate_wall_for_break_makes_break_first() -> None:
    tiles = list(range(144))
    rotated = rotate_wall_for_break(tiles, break_seat=1, break_stack=10)
    # The tile at break_seat=1, break_stack=10, layer=0 should be at index 0.
    expected_first = 1 * 36 + 10 * 2 + 0
    assert rotated[0] == expected_first
    assert len(rotated) == 144
    assert sorted(rotated) == sorted(tiles)


def test_compute_break_position_clamped() -> None:
    # dice_sum = 18 → stack = 18 - 18 = 0. The leftmost stack.
    seat, stack = compute_break_position(dealer_seat=0, dice_sum=18)
    assert stack == 0
