import numpy as np
from subterfuge.types import GameResult, Meld, MeldType

from server.hand import Hand
from server.protocol import HandPhase
from server.session import HandResult, build_hand_result_from_game


def test_build_from_winner() -> None:
    gr = GameResult(
        winner=1,
        winning_tile=5,
        is_self_draw=True,
        is_robbing_kong=False,
        tai=8,
        tai_breakdown={"门清": 2, "自摸": 1, "平胡": 5},
        payments=[-3, 9, -3, -3],
        discarder=-1,
    )
    hr = build_hand_result_from_game(gr)
    assert hr.winner_seat == 1
    assert hr.is_self_draw is True
    assert hr.is_draw is False
    assert hr.total == 8
    assert hr.payments == [-3, 9, -3, -3]
    assert hr.breakdown == {"门清": 2, "自摸": 1, "平胡": 5}
    assert hr.winning_tile == 5


def _setup_two_winners_off_same_discard() -> tuple[Hand, int]:
    """Construct a contrived scenario where seats 1 and 2 both can hu on bamboo-1.

    We bypass real play and surgically set up the state.
    """
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=0)
    h.roll_dice()
    h.deal_initial_hands()
    # Strip everything and assign a known-winning hand to seats 1 and 2.
    for s in range(4):
        h.game.players[s].hand = np.zeros(34, dtype=np.int8)
        h.game.players[s].melds.clear()
        h.game.players[s].flowers.clear()

    # Build winning hands: 5 pengs (2t,3t,4t,5t,6t) + 1t pair, waiting on 1t.
    # Pre-win = 16: 5*3 + 1 = 16, after winning tile = 17 = 5*3 + 2.
    for tid, count in [(1, 3), (2, 3), (3, 3), (4, 3), (5, 3), (0, 1)]:
        for _ in range(count):
            h.game.players[1].add_tile(tid)
            h.game.players[2].add_tile(tid)

    # Seat 0 will discard a bamboo-1.
    h.game.players[0].add_tile(0)
    # Force PLAYING.
    h.phase = HandPhase.PLAYING
    h.game.phase = __import__("subterfuge.types", fromlist=["TurnPhase"]).TurnPhase.DISCARD
    h.game.current_player = 0
    return h, 0  # h, target tile = bamboo-1


def test_multi_winner_hu_aggregates_payments() -> None:
    h, _ = _setup_two_winners_off_same_discard()
    h.apply_discard(0)
    results = h.apply_multi_hu([1, 2])
    assert len(results) == 2
    # Discarder is seat 0; winners are 1 and 2.
    aggregated = [0, 0, 0, 0]
    for r in results:
        for i in range(4):
            aggregated[i] += r.payments[i]
    # Sanity: discarder pays both winners (negative); winners gain (positive); seat 3 zero.
    assert aggregated[0] < 0
    assert aggregated[1] > 0
    assert aggregated[2] > 0
    assert aggregated[3] == 0


def test_build_from_draw() -> None:
    gr = GameResult(winner=-1)
    hr = build_hand_result_from_game(gr)
    assert hr.winner_seat is None
    assert hr.is_draw is True
    assert hr.payments == [0, 0, 0, 0]
    assert hr.total == 0
    assert hr.breakdown == {}
