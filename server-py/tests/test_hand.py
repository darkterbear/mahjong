import pytest

from server.hand import Hand
from server.protocol import HandPhase, AvailableAction
from subterfuge.tiles import FLOWER_START
from subterfuge.types import TurnPhase, MeldType
from server.protocol import HandPhase as _HP
from subterfuge.tiles import is_flower as _is_flower


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


def test_enter_playing_after_resolution() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=99)
    h.roll_dice()
    h.deal_initial_hands()
    for s in range(4):
        h.pending_flowers[s] = []
    h.enter_playing()
    assert h.phase == HandPhase.PLAYING
    assert h.game.phase == TurnPhase.DISCARD
    assert h.game.current_player == h.dealer_seat


def _fast_forward_to_playing(seed: int = 99) -> Hand:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=seed)
    h.roll_dice()
    h.deal_initial_hands()
    # Strip all pending flowers to force PLAYING transition (we don't actually
    # draw replacements — just clear them, this is a test fast-forward).
    for s in range(4):
        h.pending_flowers[s] = []
    h.enter_playing()
    assert h.phase == _HP.PLAYING
    return h


def test_dealer_starts_in_discard_after_resolution() -> None:
    h = _fast_forward_to_playing()
    assert h.game.phase == TurnPhase.DISCARD
    assert h.game.current_player == 0


def test_discard_advances_to_claim_window() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    assert h.game.phase == TurnPhase.CLAIM_WINDOW
    assert h.game.last_discard == tile
    assert h.game.last_discard_player == 0


def test_draw_front_advances_to_discard() -> None:
    h = _fast_forward_to_playing()
    # Discard so it's seat 1's turn to draw.
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.close_claim_window_no_winner()
    assert h.game.current_player == 1
    drawn = h.draw_front()
    assert drawn is not None
    assert h.game.phase == TurnPhase.DISCARD



def test_apply_peng_claim_moves_turn_to_claimer() -> None:
    h = _fast_forward_to_playing()
    # Set up: seat 0 will discard a tile, seat 2 has 2 of those tiles in hand.
    p2 = h.game.players[2]
    target_tile = 0  # bamboo-1
    while p2.hand[target_tile] < 2:
        p2.add_tile(target_tile)
    p0 = h.game.players[0]
    p0.add_tile(target_tile)
    h.apply_discard(target_tile)
    h.apply_claim(seat=2, claim_type="peng")
    assert h.game.current_player == 2
    assert h.game.phase == TurnPhase.DISCARD
    assert any(m.meld_type == MeldType.PENG for m in h.game.players[2].melds)


def test_apply_chi_claim_only_for_left_neighbor() -> None:
    h = _fast_forward_to_playing()
    # Seat 0 discards, seat 1 (left neighbor in TW: discarder + 1) attempts chi.
    p1 = h.game.players[1]
    p1.add_tile(1)  # bamboo-2
    p1.add_tile(2)  # bamboo-3
    h.game.players[0].add_tile(0)  # bamboo-1
    h.apply_discard(0)
    h.apply_claim(seat=1, claim_type="chi", tiles=[1, 2])
    assert h.game.current_player == 1


def test_apply_hu_claim_ends_hand() -> None:
    # Stub — covered comprehensively in scoring tests (Phase 5).
    pass


def test_declare_concealed_gang() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    # Force 4 of bamboo-1 in seat 0's hand.
    while p.hand[0] < 4:
        p.add_tile(0)
    h.declare_concealed_gang(0)
    assert any(m.meld_type == MeldType.GANG_CONCEALED for m in p.melds)
    assert h.game.phase == TurnPhase.DRAW
    assert h.must_draw_back is True


def test_declare_added_gang_opens_robbing_window() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    # Seat 0 already has a peng of bamboo-2 + holds a 4th tile in hand.
    from subterfuge.types import Meld, MeldType
    p.melds.append(Meld(meld_type=MeldType.PENG, tiles=[1, 1, 1], source_player=3))
    p.add_tile(1)
    h.declare_added_gang(1)
    assert h.game.phase == TurnPhase.CLAIM_WINDOW
    assert h.game._pending_gang_add is not None


def test_added_gang_completes_when_window_closes() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    from subterfuge.types import Meld, MeldType
    p.melds.append(Meld(meld_type=MeldType.PENG, tiles=[1, 1, 1], source_player=3))
    p.add_tile(1)
    h.declare_added_gang(1)
    # No eligible robbers in this synthetic scenario — caller-equivalent of
    # the socket handler closes the window immediately.
    h.close_claim_window_no_winner()
    assert h.game._pending_gang_add is None
    # The PENG meld should now be a GANG_ADD.
    assert any(m.meld_type == MeldType.GANG_ADD for m in p.melds)
    assert h.must_draw_back is True


def test_available_actions_pre_dice() -> None:
    h = Hand(dealer_seat=2, round_wind_index=0, dealer_streak=0, seed=0)
    assert h.available_actions(2) == [AvailableAction.ROLL_DICE]
    assert h.available_actions(0) == []


def test_available_actions_flower_resolution() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=1)
    h.roll_dice()
    h.deal_initial_hands()
    assert h.available_actions(0) == []


def test_available_actions_playing_current_player_in_draw() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.close_claim_window_no_winner()
    # Seat 1 is now current player in DRAW.
    actions = h.available_actions(1)
    assert AvailableAction.DRAW_FRONT in actions


def test_available_actions_playing_current_player_in_discard() -> None:
    h = _fast_forward_to_playing()
    actions = h.available_actions(0)
    # Has many discard options + maybe self-actions.
    # Just check that DISCARD is exposed (the action bar lights up tiles).
    assert AvailableAction.DISCARD in actions



def test_available_actions_in_claim_window() -> None:
    h = _fast_forward_to_playing()
    p2 = h.game.players[2]
    while p2.hand[0] < 2:
        p2.add_tile(0)
    h.game.players[0].add_tile(0)
    h.apply_discard(0)
    actions_2 = h.available_actions(2)
    assert AvailableAction.PENG in actions_2


def test_can_hu_on_tile_basic() -> None:
    h = _fast_forward_to_playing()
    import numpy as np
    p = h.game.players[1]
    p.hand = np.zeros(34, dtype=np.int8)
    for tid, count in [(1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (0, 1)]:
        for _ in range(count):
            p.add_tile(tid)
    assert h.can_hu_on_tile(1, 0) is True
    assert h.can_hu_on_tile(1, 9) is False




def test_peng_removes_tile_from_discarders_pile() -> None:
    h = _fast_forward_to_playing()
    p0 = h.game.players[0]
    p2 = h.game.players[2]
    target = 0
    while p2.hand[target] < 2:
        p2.add_tile(target)
    p0.add_tile(target)
    pre_discard_count = len(p0.discards)
    h.apply_discard(target)
    # After discard, discard pile grew by 1.
    assert len(p0.discards) == pre_discard_count + 1
    # Peng claim removes the tile from discarder's pile.
    h.apply_claim(seat=2, claim_type="peng")
    assert len(p0.discards) == pre_discard_count


def test_auto_resolve_round_drains_pending_for_seat() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=0)
    h.roll_dice()
    h.deal_initial_hands()
    h.pending_flowers[0] = [34, 35]  # 2 pending flowers
    steps = h.auto_resolve_round_for_seat(0)
    assert len(steps) == 2  # both resolved this round
    assert h.game.players[0].flowers[-2:] == [34, 35]


def test_auto_resolve_round_defers_replacement_flower_to_next_round() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=0)
    h.roll_dice()
    h.deal_initial_hands()
    h.pending_flowers[0] = [34]
    # Force the back-of-wall tile to be a flower.
    h.game.wall.tiles[h.game.wall._back] = 35
    steps = h.auto_resolve_round_for_seat(0)
    assert len(steps) == 1
    assert steps[0]["replacement"] == 35
    assert steps[0]["replacement_is_flower"] is True
    # The new flower waits for the next round; it should NOT be in this-round steps.
    assert h.pending_flowers[0] == [35]


# ---- ClaimWindow tests -------------------------------------------------------

def test_claim_window_opens_on_discard() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.open_claim_window(discarder=0, tile=tile, is_robbing_kong=False)
    assert h.claim_window is not None
    assert h.claim_window.pending_seats == {1, 2, 3}


def test_claim_window_records_pass() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.open_claim_window(discarder=0, tile=tile, is_robbing_kong=False)
    h.record_claim_decision(1, {"action": "pass"})
    assert 1 not in h.claim_window.pending_seats
    assert h.claim_window.decisions[1] == {"action": "pass"}


def test_claim_window_wait_blocks_resolution() -> None:
    import time
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.open_claim_window(discarder=0, tile=tile, is_robbing_kong=False)
    # All seats pass except seat 2 which is in wait mode.
    h.record_claim_decision(1, {"action": "pass"})
    h.record_claim_decision(3, {"action": "pass"})
    h.record_wait_toggle(2, True)
    # Force >= 2s elapsed (manipulate started_at).
    h.claim_window.started_at = time.monotonic() - 5.0
    assert not h.claim_window_resolvable()  # waiters block
    h.record_wait_toggle(2, False)
    # Still pending — seat 2 hasn't decided.
    assert not h.claim_window_resolvable()
    h.record_claim_decision(2, {"action": "pass"})
    assert h.claim_window_resolvable()


def test_claim_window_not_resolvable_before_2s() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.open_claim_window(discarder=0, tile=tile, is_robbing_kong=False)
    # All seats pass immediately, but < 2s elapsed.
    h.record_claim_decision(1, {"action": "pass"})
    h.record_claim_decision(2, {"action": "pass"})
    h.record_claim_decision(3, {"action": "pass"})
    # pending_seats is empty, waiters empty, but < 2s → not resolvable yet.
    assert not h.claim_window_resolvable()


def test_claim_window_close_clears_state() -> None:
    h = _fast_forward_to_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.open_claim_window(discarder=0, tile=tile, is_robbing_kong=False)
    assert h.claim_window is not None
    h.close_claim_window()
    assert h.claim_window is None
