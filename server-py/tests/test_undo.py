import copy

from server.hand import Hand
from server.protocol import HandPhase
from subterfuge.types import TurnPhase


def _setup_playing(seed: int = 7) -> Hand:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=seed)
    h.roll_dice()
    h.deal_initial_hands()
    for s in range(4):
        h.pending_flowers[s] = []
    h.flower_resolution_seat = 0
    h._maybe_finish_flower_resolution()
    return h


def test_snapshot_and_undo_one_action() -> None:
    h = _setup_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    pre_hand_count = p.hand_count
    h.snapshot()
    h.apply_discard(tile)
    assert h.game.phase == TurnPhase.CLAIM_WINDOW
    h.undo()
    assert h.game.phase == TurnPhase.DISCARD
    assert h.game.players[0].hand_count == pre_hand_count


def test_undo_chain() -> None:
    h = _setup_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    initial_state = (h.game.phase, p.hand_count)

    h.snapshot()
    h.apply_discard(tile)
    h.snapshot()
    h.close_claim_window_no_winner()
    h.snapshot()
    h.draw_front()

    # Walk back 3 times.
    h.undo()
    h.undo()
    h.undo()
    assert (h.game.phase, h.game.players[0].hand_count) == initial_state


def test_undo_empty_stack_raises() -> None:
    import pytest
    h = _setup_playing()
    with pytest.raises(RuntimeError):
        h.undo()


def test_clear_snapshots_on_settlement() -> None:
    h = _setup_playing()
    h.snapshot()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    h.phase = HandPhase.SETTLEMENT
    h.clear_snapshots()
    assert len(h._snapshots) == 0
