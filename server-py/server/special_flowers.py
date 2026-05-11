"""八仙过海 (Eight Immortals) and 七抢一 (Seven Stealing One) detection.

Replicates the logic in subterfuge.engine.game._check_flower_special_wins so
we don't depend on subterfuge's internal API.
"""
from __future__ import annotations

ALL_FLOWERS = set(range(34, 42))


def detect_special_flower_win(
    per_seat_flowers: list[list[int]],
    ruleset_triggers_seven_steal: bool,
) -> tuple[int, int | None] | None:
    """Return (winner_seat, sole_payer_seat) if a special flower win is met.

    sole_payer_seat is None for 八仙过海 (everyone pays), set for 七抢一.
    Returns None if no special condition met.
    """
    # 八仙过海 — any player with all 8 unique flowers.
    for seat, flowers in enumerate(per_seat_flowers):
        if len(set(flowers)) == 8:
            return seat, None

    if not ruleset_triggers_seven_steal:
        return None

    # 七抢一 — one player has 7 unique flowers, another has the 8th.
    for seat, flowers in enumerate(per_seat_flowers):
        unique = set(flowers)
        if len(unique) != 7:
            continue
        missing = ALL_FLOWERS - unique
        if len(missing) != 1:
            continue
        missing_tile = next(iter(missing))
        for other_seat, other_flowers in enumerate(per_seat_flowers):
            if other_seat == seat:
                continue
            if missing_tile in other_flowers:
                return seat, other_seat
    return None
