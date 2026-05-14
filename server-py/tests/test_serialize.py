from server.hand import Hand
from server.protocol import HandPhase
from server.serialize import build_state_update


def _setup_playing(seed: int = 0) -> Hand:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=seed)
    h.roll_dice()
    h.deal_initial_hands()
    for s in range(4):
        h.pending_flowers[s] = []
    h.enter_playing()
    return h


def test_state_update_basic_shape_for_seat_0() -> None:
    h = _setup_playing()
    seats = ["alice", "bob", "charlie", "dan"]
    s = build_state_update(
        hand=h, viewer_seat=0, seats=seats,
        cumulative_scores=[5, -1, -2, -2],
        round_wind_index=h.round_wind_index,
        dealer_streak=h.dealer_streak,
    )
    assert s["phase"] == "PLAYING"
    assert s["dealer_seat"] == 0
    assert s["current_turn_seat"] == 0
    assert s["you"]["seat"] == 0
    assert s["you"]["score"] == 5
    assert isinstance(s["you"]["hand"], list)
    # Three "others" entries in counterclockwise order from viewer.
    assert len(s["others"]) == 3
    assert s["others"][0]["seat"] == 1
    assert s["others"][0]["username"] == "bob"
    assert "hand_count" in s["others"][0]
    assert "hand" not in s["others"][0]


def test_state_update_pending_claim_window() -> None:
    h = _setup_playing()
    p2 = h.game.players[2]
    while p2.hand[0] < 2:
        p2.add_tile(0)
    h.game.players[0].add_tile(0)
    h.apply_discard(0)
    # Open the new-style ClaimWindow.
    h.open_claim_window(discarder=0, tile=0, is_robbing_kong=False)
    s = build_state_update(
        hand=h, viewer_seat=2, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["pending_claim_window"] is not None
    assert s["pending_claim_window"]["discarder_seat"] == 0
    assert s["pending_claim_window"]["tile"] == 0
    assert "peng" in s["pending_claim_window"]["your_options"]


def test_state_update_wall_positions_present() -> None:
    h = _setup_playing()
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert "wall" in s
    nf = s["wall"]["next_front_position"]
    assert nf is None or (isinstance(nf, list) and len(nf) == 3)


def test_state_update_includes_pending_flowers_in_own_hand() -> None:
    h = _setup_playing()
    # Inject a pending flower for the viewer.
    h.pending_flowers[0].append(34)
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    # The flower (id 34) appears in viewer's hand, not in flowers row.
    assert 34 in s["you"]["hand"]
    assert 34 not in s["you"]["flowers"]


def test_state_update_other_hand_count_includes_pending_flowers() -> None:
    h = _setup_playing()
    h.pending_flowers[1].append(34)
    h.pending_flowers[1].append(35)
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    other_seat_1 = next(o for o in s["others"] if o["seat"] == 1)
    expected = int(h.game.players[1].hand.sum()) + 2  # +2 pending flowers
    assert other_seat_1["hand_count"] == expected


def test_state_update_wall_position_respects_dice_rotation() -> None:
    """After dice rotation, next_front_position should report the break stack's TOP layer."""
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    h.roll_dice()
    expected_seat = h.dice_result.break_seat
    # compute_break_position gives stack = 18 - dice_sum (clamped).
    from server.dice import compute_break_position
    _, expected_stack = compute_break_position(0, h.dice_result.sum)
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["wall"]["next_front_position"] == [expected_seat, expected_stack, 0]


def test_state_update_robbing_kong_window_flag() -> None:
    h = _setup_playing()
    p = h.game.players[0]
    # Seat 0 has a peng of bamboo-2 + holds the 4th in hand → can add-kong.
    from subterfuge.types import Meld, MeldType
    p.melds.append(Meld(meld_type=MeldType.PENG, tiles=[1, 1, 1], source_player=3))
    p.add_tile(1)
    # Set up seat 2 with a hand that wins on tile 1 (so they CAN rob).
    import numpy as np
    p2 = h.game.players[2]
    p2.hand = np.zeros(34, dtype=np.int8)
    for tid, count in [(0, 3), (2, 3), (3, 3), (4, 3), (5, 3), (1, 1)]:
        for _ in range(count):
            p2.add_tile(tid)
    h.declare_added_gang(1)
    tile = h.game.last_discard
    declarer = h.game.last_discard_player
    h.open_claim_window(discarder=declarer, tile=tile, is_robbing_kong=True)
    # Seat 2 has an eligible Hu on tile 1 → should see the claim window.
    s = build_state_update(
        hand=h, viewer_seat=2, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["pending_claim_window"] is not None
    assert s["pending_claim_window"]["is_robbing_kong_window"] is True

    # The discarder (seat 0) should NOT see the pending_claim_window.
    s0 = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s0["pending_claim_window"] is None


def test_state_update_normal_claim_window_not_robbing() -> None:
    h = _setup_playing()
    p2 = h.game.players[2]
    while p2.hand[0] < 2:
        p2.add_tile(0)
    h.game.players[0].add_tile(0)
    h.apply_discard(0)
    h.open_claim_window(discarder=0, tile=0, is_robbing_kong=False)
    s = build_state_update(
        hand=h, viewer_seat=2, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["pending_claim_window"] is not None
    assert s["pending_claim_window"]["is_robbing_kong_window"] is False


def test_current_turn_seat_in_flower_resolution() -> None:
    h = Hand(dealer_seat=2, round_wind_index=0, dealer_streak=0, seed=1)
    h.roll_dice()
    h.deal_initial_hands()
    # During FLOWER_RESOLUTION, current_turn_seat should reflect the dealer_seat.
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["current_turn_seat"] == h.dealer_seat


def test_other_player_pending_flowers_exposed() -> None:
    h = _setup_playing()
    h.pending_flowers[1].append(35)
    h.pending_flowers[1].append(38)
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    other_seat_1 = next(o for o in s["others"] if o["seat"] == 1)
    assert other_seat_1["pending_flowers"] == [35, 38]


def test_current_turn_advances_to_next_player_during_claim_window() -> None:
    h = _setup_playing()
    p = h.game.players[0]
    tile = next(t for t in range(34) if p.hand[t] > 0)
    h.apply_discard(tile)
    # Now in CLAIM_WINDOW; current turn should point at seat 1.
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a", "b", "c", "d"],
        cumulative_scores=[0, 0, 0, 0], round_wind_index=0, dealer_streak=0,
    )
    assert s["current_turn_seat"] == 1


def test_wall_back_draws_top_layer_first_per_stack() -> None:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    h.roll_dice()
    h.game.wall.draw_replacement()
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    nb = s["wall"]["next_back_position"]
    assert nb is not None
    assert nb[2] == 1  # bottom layer, since top was drawn first


def test_wall_front_advances_clockwise() -> None:
    """After one front draw, the next_front_position should still be the
    bottom of the break stack (top first). After two front draws, the next
    position should be the TOP of the stack ONE CW (decreasing physical stack)
    from the break."""
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    h.roll_dice()
    # First draw: pops the top of the break stack.
    h.game.wall.draw()
    s1 = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    break_seat = h.dice_result.break_seat
    from server.dice import compute_break_position
    _, break_stack = compute_break_position(0, h.dice_result.sum)
    assert s1["wall"]["next_front_position"] == [break_seat, break_stack, 1]
    # Second draw: pops the bottom; next position should be the TOP of the
    # stack one CW from break.
    h.game.wall.draw()
    s2 = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    nf = s2["wall"]["next_front_position"]
    # CW = decreasing physical stack index (mod 72). With offset = break_seat*36+break_stack*2,
    # break_stack_global = offset // 2 = break_seat*18 + break_stack.
    # Next stack CW = (break_stack_global - 1) % 72; convert to (seat, stack).
    NUM_STACKS = 72
    break_stack_global = break_seat * 18 + break_stack
    next_stack_global = (break_stack_global - 1) % NUM_STACKS
    expected_seat = next_stack_global // 18
    expected_stack = next_stack_global % 18
    assert nf == [expected_seat, expected_stack, 0]


def test_pending_claim_window_exposes_chi_combos() -> None:
    h = _setup_playing()
    # Seat 1 will be eligible for chi from seat 0's discard.
    p1 = h.game.players[1]
    # Give seat 1 a full-enough hand that includes bamboo-2 and bamboo-4 so it
    # can chi bamboo-3. Chi requires a realistically-sized hand to be offered.
    import numpy as np
    p1.hand = np.zeros(34, dtype=np.int8)
    for tid in [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]:
        p1.add_tile(tid)
    p1.add_tile(1)  # bamboo-2
    p1.add_tile(3)  # bamboo-4
    h.game.players[0].add_tile(2)  # bamboo-3 for seat 0 to discard
    h.apply_discard(2)
    h.open_claim_window(discarder=0, tile=2, is_robbing_kong=False)
    s = build_state_update(
        hand=h, viewer_seat=1, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    pcw = s["pending_claim_window"]
    assert pcw is not None
    assert "chi_combos" in pcw
    assert [1, 3] in pcw["chi_combos"]


def test_drawn_tile_appended_at_end_of_own_hand() -> None:
    h = _setup_playing()
    # Force seat 0 to be in DISCARD phase having just drawn a known tile.
    import numpy as np
    p = h.game.players[0]
    p.hand = np.zeros(34, dtype=np.int8)
    for tid in [0, 2, 5, 10]:
        p.add_tile(tid)
    # Mark tile 5 as the just-drawn (manually, simulating draw_front result).
    p._just_drew = 5
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    # Hand should end with the drawn tile (5).
    assert s["you"]["hand"][-1] == 5
    # The OTHER tiles should appear sorted before it.
    assert s["you"]["hand"][:-1] == [0, 2, 10]


def test_drawn_tile_resorts_after_discard() -> None:
    h = _setup_playing()
    import numpy as np
    p = h.game.players[0]
    p.hand = np.zeros(34, dtype=np.int8)
    for tid in [0, 2, 5, 10]:
        p.add_tile(tid)
    p._just_drew = 5
    h.apply_discard(5)
    # After discard, _just_drew is reset; hand re-sorts naturally.
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["you"]["hand"] == [0, 2, 10]


def test_state_update_exposes_kong_eligible_tiles() -> None:
    h = _setup_playing()
    p = h.game.players[0]
    # 4 of bamboo-1 → concealed gang eligible
    while p.hand[0] < 4:
        p.add_tile(0)
    # peng of bamboo-2 + 1 in hand → added gang eligible
    from subterfuge.types import Meld, MeldType
    p.melds.append(Meld(meld_type=MeldType.PENG, tiles=[1, 1, 1], source_player=3))
    p.add_tile(1)
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert 0 in s["you"]["concealed_gang_tiles"]
    assert 1 in s["you"]["added_gang_tiles"]


