import pytest

from server.hand import Hand
from server.protocol import HandPhase


def test_hand_starts_in_pre_dice() -> None:
    hand = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    assert hand.phase == HandPhase.PRE_DICE
    assert hand.dealer_seat == 0
    assert hand.dice_result is None


def test_roll_dice_advances_to_dealing() -> None:
    hand = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    hand.roll_dice()
    assert hand.phase == HandPhase.DEALING
    assert hand.dice_result is not None
    assert hand.dice_result.break_seat in range(4)


def test_roll_dice_twice_raises() -> None:
    hand = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    hand.roll_dice()
    with pytest.raises(RuntimeError):
        hand.roll_dice()


def test_finish_dealing_advances_to_flower_resolution() -> None:
    hand = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    hand.roll_dice()
    hand.deal_initial_hands()
    assert hand.phase == HandPhase.FLOWER_RESOLUTION
    # Each non-dealer has 16 tiles; dealer has 17.
    counts = [hand.game.players[s].hand_count for s in range(4)]
    assert sum(counts) == 16 * 3 + 17
    assert counts[hand.dealer_seat] == 17
