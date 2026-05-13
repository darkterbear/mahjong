from server.special_flowers import detect_special_flower_win


def test_no_special_when_few_flowers() -> None:
    assert detect_special_flower_win(
        per_seat_flowers=[[34, 35], [], [36], []],
        ruleset_triggers_seven_steal=True,
    ) is None


def test_eight_immortals() -> None:
    eight = list(range(34, 42))
    result = detect_special_flower_win(
        per_seat_flowers=[eight, [], [], []],
        ruleset_triggers_seven_steal=True,
    )
    assert result == (0, None)  # winner seat 0, all pay


def test_seven_stealing_one() -> None:
    # Seat 1 has 7 unique flowers, seat 3 has the missing 8th
    seven = list(range(34, 41))           # 34..40
    missing = 41
    result = detect_special_flower_win(
        per_seat_flowers=[[], seven, [], [missing]],
        ruleset_triggers_seven_steal=True,
    )
    assert result == (1, 3)


def test_seven_stealing_one_disabled() -> None:
    seven = list(range(34, 41))
    result = detect_special_flower_win(
        per_seat_flowers=[[], seven, [], [41]],
        ruleset_triggers_seven_steal=False,
    )
    assert result is None
