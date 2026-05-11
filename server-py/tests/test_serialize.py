from server.hand import Hand
from server.protocol import HandPhase
from server.serialize import build_state_update


def _setup_playing(seed: int = 0) -> Hand:
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=seed)
    h.roll_dice()
    h.deal_initial_hands()
    for s in range(4):
        h.pending_flowers[s] = []
    h.flower_resolution_seat = 0
    h._maybe_finish_flower_resolution()
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
    """After dice rotation, next_front_position should report the physical break point."""
    h = Hand(dealer_seat=0, round_wind_index=0, dealer_streak=0, seed=42)
    h.roll_dice()
    # Record the dice break for comparison.
    expected_seat = h.dice_result.break_seat
    expected_stack = (17 - min(h.dice_result.sum, 17))
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    nf = s["wall"]["next_front_position"]
    assert nf == [expected_seat, expected_stack, 0], \
        f"expected [{expected_seat}, {expected_stack}, 0], got {nf}"


def test_state_update_robbing_kong_window_flag() -> None:
    h = _setup_playing()
    p = h.game.players[0]
    # Seat 0 has a peng of bamboo-2 + holds the 4th in hand → can add-kong.
    from subterfuge.types import Meld, MeldType
    p.melds.append(Meld(meld_type=MeldType.PENG, tiles=[1, 1, 1], source_player=3))
    p.add_tile(1)
    h.declare_added_gang(1)
    # From seat 2's POV (a non-discarder), the pending claim window should be flagged.
    s = build_state_update(
        hand=h, viewer_seat=2, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["pending_claim_window"] is not None
    assert s["pending_claim_window"]["is_robbing_kong_window"] is True


def test_state_update_normal_claim_window_not_robbing() -> None:
    h = _setup_playing()
    p2 = h.game.players[2]
    while p2.hand[0] < 2:
        p2.add_tile(0)
    h.game.players[0].add_tile(0)
    h.apply_discard(0)
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
    # During FLOWER_RESOLUTION, current_turn_seat should reflect flower_resolution_seat.
    s = build_state_update(
        hand=h, viewer_seat=0, seats=["a","b","c","d"],
        cumulative_scores=[0,0,0,0], round_wind_index=0, dealer_streak=0,
    )
    assert s["current_turn_seat"] == h.flower_resolution_seat


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
