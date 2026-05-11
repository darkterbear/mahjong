from subterfuge.types import GameResult

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


def test_build_from_draw() -> None:
    gr = GameResult(winner=-1)
    hr = build_hand_result_from_game(gr)
    assert hr.winner_seat is None
    assert hr.is_draw is True
    assert hr.payments == [0, 0, 0, 0]
    assert hr.total == 0
    assert hr.breakdown == {}
