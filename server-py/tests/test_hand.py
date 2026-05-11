import pytest

from server.hand import Hand
from server.protocol import HandPhase
from subterfuge.tiles import FLOWER_START
from subterfuge.types import TurnPhase


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
    # Each non-dealer received 16 tiles (some may be pending flowers); dealer received 17.
    counts = [
        hand.game.players[s].hand_count + len(hand.pending_flowers[s])
        for s in range(4)
    ]
    assert sum(counts) == 16 * 3 + 17
    assert counts[hand.dealer_seat] == 17


def _force_flower_into_pending(hand: Hand, seat: int, flower_id: int) -> None:
    """Helper: surgically inject a flower into a seat's pending-flowers list."""
    hand.pending_flowers[seat].append(flower_id)


def test_flower_resolution_turn_order_dealer_first() -> None:
    h = Hand(dealer_seat=2, round_wind_index=0, dealer_streak=0, seed=1)
    h.roll_dice()
    h.deal_initial_hands()
    assert h.flower_resolution_seat == 2  # dealer first


def test_declare_flower_then_draw_back_loops() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=1)
    h.roll_dice()
    h.deal_initial_hands()
    # Force a flower in seat 0's pending for deterministic test.
    _force_flower_into_pending(h, 0, FLOWER_START)
    initial_pending = len(h.pending_flowers[0])
    initial_player_hand = h.game.players[0].hand_count
    h.flower_resolution_seat = 0
    h.declare_flower(FLOWER_START)
    # Pending list lost one flower; player.flowers got it.
    assert len(h.pending_flowers[0]) == initial_pending - 1
    assert FLOWER_START in h.game.players[0].flowers
    assert h.must_draw_back is True
    h.draw_back()
    # After draw_back, total tiles owned by seat 0 is back to original (one
    # replacement tile arrived in either pending_flowers or game.hand).
    new_total = h.game.players[0].hand_count + len(h.pending_flowers[0])
    assert new_total == initial_player_hand + initial_pending  # one replacement


def test_flower_resolution_advances_when_seat_clean() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=1)
    h.roll_dice()
    h.deal_initial_hands()
    # Force seat 0 to be flower-free; seed=1 ensures seat 1 has pending flowers.
    h.pending_flowers[0] = []
    h.flower_resolution_seat = 0
    h._advance_flower_resolution_seat_if_clean()
    assert h.flower_resolution_seat == 1  # advances and stops at seat with pending


def test_finish_flower_resolution_transitions_to_playing() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=99)
    h.roll_dice()
    h.deal_initial_hands()
    # Fast-forward by clearing all pending flowers.
    for s in range(4):
        h.pending_flowers[s] = []
    h.flower_resolution_seat = h.dealer_seat
    h._maybe_finish_flower_resolution()
    assert h.phase == HandPhase.PLAYING
    assert h.game.phase == TurnPhase.DISCARD
    assert h.game.current_player == h.dealer_seat
