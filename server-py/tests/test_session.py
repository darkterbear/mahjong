import pytest

from server.session import Session, HandResult


def test_session_initial_state() -> None:
    s = Session(player_ids=["a", "b", "c", "d"], seed=0)
    assert len(s.seats) == 4
    assert sorted(s.seats) == ["a", "b", "c", "d"]
    assert s.dealer_seat == 0
    assert s.dealer_streak == 0
    assert s.round_wind_index == 0
    assert s.cumulative_scores == [0, 0, 0, 0]
    assert s.current_hand is None


def test_session_seats_are_random() -> None:
    s1 = Session(player_ids=["a", "b", "c", "d"], seed=1)
    s2 = Session(player_ids=["a", "b", "c", "d"], seed=2)
    assert s1.seats != s2.seats or s1.seats != ["a", "b", "c", "d"]


def test_start_new_hand_creates_hand() -> None:
    s = Session(player_ids=["a", "b", "c", "d"], seed=0)
    s.start_new_hand()
    assert s.current_hand is not None
    assert s.current_hand.dealer_seat == s.dealer_seat


def test_record_settlement_updates_scores_and_dealer_keeps_on_self_draw() -> None:
    s = Session(player_ids=["a", "b", "c", "d"], seed=0)
    s.start_new_hand()
    result = HandResult(
        winner_seat=s.dealer_seat,
        is_self_draw=True,
        is_draw=False,
        payments=[3, -1, -1, -1],
        breakdown={"自摸": 1, "门清": 2},
        total=3,
    )
    s.record_settlement(result)
    assert s.cumulative_scores == [3, -1, -1, -1]
    assert s.dealer_streak == 1
    assert s.dealer_seat == 0  # kept


def test_record_settlement_rotates_on_non_dealer_win() -> None:
    s = Session(player_ids=["a", "b", "c", "d"], seed=0)
    s.start_new_hand()
    non_dealer = (s.dealer_seat + 1) % 4
    result = HandResult(
        winner_seat=non_dealer, is_self_draw=False, is_draw=False,
        payments=[0, 5, 0, -5], breakdown={}, total=5,
    )
    initial_dealer = s.dealer_seat
    s.record_settlement(result)
    assert s.dealer_seat == (initial_dealer + 1) % 4
    assert s.dealer_streak == 0


def test_round_wind_advances_after_full_dealer_cycle() -> None:
    s = Session(player_ids=["a", "b", "c", "d"], seed=0)
    initial_wind = s.round_wind_index
    for _ in range(4):
        s.start_new_hand()
        s.record_settlement(HandResult(
            winner_seat=(s.dealer_seat + 1) % 4,
            is_self_draw=False, is_draw=False,
            payments=[0, 0, 0, 0], breakdown={}, total=0,
        ))
    assert s.round_wind_index == (initial_wind + 1) % 4


def test_record_settlement_draw_increments_streak() -> None:
    s = Session(player_ids=["a", "b", "c", "d"], seed=0)
    s.start_new_hand()
    s.record_settlement(HandResult(
        winner_seat=None, is_self_draw=False, is_draw=True,
        payments=[0, 0, 0, 0], breakdown={}, total=0,
    ))
    assert s.dealer_streak == 1
    assert s.dealer_seat == 0


def test_record_multi_settlement_aggregates() -> None:
    s = Session(player_ids=["a","b","c","d"], seed=0)
    s.start_new_hand()
    r1 = HandResult(winner_seat=1, is_self_draw=False, is_draw=False,
                    payments=[-5, 5, 0, 0], breakdown={}, total=5)
    r2 = HandResult(winner_seat=2, is_self_draw=False, is_draw=False,
                    payments=[-3, 0, 3, 0], breakdown={}, total=3)
    s.record_multi_settlement([r1, r2])
    assert s.cumulative_scores == [-8, 5, 3, 0]
    # Two non-dealer wins → dealer rotates once (rotation triggered by FIRST win).
    assert s.dealer_seat == 1
