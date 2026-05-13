"""Build per-player state_update JSON dicts."""
from __future__ import annotations

from typing import Optional

from subterfuge.tiles import is_flower
from subterfuge.types import Wind, TurnPhase

from server.hand import Hand
from server.protocol import HandPhase, AvailableAction
from server.wall_view import flat_to_position, TILES_PER_SEAT, TOTAL_WALL_TILES

WIND_NAMES = ["EAST", "SOUTH", "WEST", "NORTH"]


def _active_seat(hand: Hand) -> int:
    if hand.phase in (HandPhase.PRE_DICE, HandPhase.FLOWER_RESOLUTION):
        return hand.dealer_seat
    # During an open claim window, the "active" seat is the player who would
    # draw next once the window closes (i.e., the seat counterclockwise of the
    # discarder). Subterfuge's current_player still points at the discarder
    # until the claim resolves.
    if hand.game.phase == TurnPhase.CLAIM_WINDOW and hand.game.last_discard_player is not None:
        return (hand.game.last_discard_player + 1) % 4
    return hand.game.current_player


def build_state_update(
    hand: Hand,
    viewer_seat: int,
    seats: list[str],            # player usernames in seat order
    cumulative_scores: list[int],
    round_wind_index: int,
    dealer_streak: int,
) -> dict:
    """Return the JSON dict for `state_update` from viewer_seat's POV."""
    you_player = hand.game.players[viewer_seat]
    drawn = you_player._just_drew
    # Build hand list. If the player just drew a non-flower (i.e., they're in
    # DISCARD phase awaiting discard), pull that tile out of the sorted hand
    # and append it at the end so it's clearly the freshly-drawn tile.
    if drawn is not None and 0 <= drawn < 34 and you_player.hand[drawn] > 0:
        # Build the hand WITHOUT one instance of `drawn`.
        sorted_hand: list[int] = []
        for tid in range(34):
            count = int(you_player.hand[tid])
            if tid == drawn:
                count -= 1  # leave one out
            sorted_hand.extend([tid] * count)
        you_hand = sorted_hand + [drawn] + list(hand.pending_flowers[viewer_seat])
    else:
        you_hand = _hand_as_list(you_player.hand) + list(hand.pending_flowers[viewer_seat])
    you = {
        "seat": viewer_seat,
        "seat_wind": _seat_wind_name(viewer_seat, hand.dealer_seat),
        "username": seats[viewer_seat],
        "hand": you_hand,
        "melds": [_meld_dict(m) for m in you_player.melds],
        "flowers": list(you_player.flowers),
        "discards": list(you_player.discards),
        "drawn_tile": you_player._just_drew,
        "score": cumulative_scores[viewer_seat],
        "concealed_gang_tiles": list(you_player.can_gang_self()),
        "added_gang_tiles": list(you_player.can_gang_add()),
    }

    others = []
    for offset in range(1, 4):
        s = (viewer_seat + offset) % 4
        op = hand.game.players[s]
        others.append({
            "seat": s,
            "seat_wind": _seat_wind_name(s, hand.dealer_seat),
            "username": seats[s],
            "hand_count": int(op.hand.sum()) + len(hand.pending_flowers[s]),
            "pending_flowers": list(hand.pending_flowers[s]),
            "melds": [_meld_dict(m) for m in op.melds],
            "flowers": list(op.flowers),
            "discards": list(op.discards),
            "score": cumulative_scores[s],
        })

    wall = _wall_payload(hand)
    pending = _pending_claim_window(hand, viewer_seat)
    available = [a.value for a in hand.available_actions(viewer_seat)]

    pending_co_hu = None
    if hand.co_hu_active:
        pending_co_hu = {
            "tile": hand.game.last_discard,
            "discarder_seat": hand.game.last_discard_player,
            "joined_seats": list(hand.co_hu_joined),
            "remaining_seats": list(hand.co_hu_remaining),
            "declined_seats": list(hand.co_hu_declined),
        }

    return {
        "phase": hand.phase.value,
        "round_wind": WIND_NAMES[round_wind_index],
        "dealer_seat": hand.dealer_seat,
        "dealer_streak": dealer_streak,
        "current_turn_seat": _active_seat(hand),
        "you": you,
        "others": others,
        "wall": wall,
        "available_actions": available,
        "pending_claim_window": pending,
        "pending_co_hu": pending_co_hu,
        "can_undo": len(hand._snapshots) > 0,
        "event_log": list(hand.event_log),
    }


def _hand_as_list(hand_counts) -> list[int]:
    out = []
    for tid in range(len(hand_counts)):
        out.extend([tid] * int(hand_counts[tid]))
    return out


def _meld_dict(meld) -> dict:
    return {
        "type": meld.meld_type.name,
        "tiles": list(meld.tiles),
        "source_seat": meld.source_player,
    }


def _seat_wind_name(seat: int, dealer_seat: int) -> str:
    return WIND_NAMES[(seat - dealer_seat) % 4]


NUM_STACKS = 72  # 4 seats × 18 stacks


def _wall_payload(hand: Hand) -> dict:
    wall = hand.game.wall
    total = len(wall.tiles)
    front_drawn = wall._front
    back_drawn = (total - 1) - wall._back
    rem = max(0, total - front_drawn - back_drawn)
    offset = hand.wall_rotation_offset
    if rem == 0:
        return {
            "remaining": 0,
            "next_front_position": None,
            "next_back_position": None,
            "remaining_positions": [],
        }
    break_stack = offset // 2  # physical stack index (0..71) of the break

    front_full_stacks = front_drawn // 2
    front_partial_top_gone = (front_drawn % 2) == 1
    back_full_stacks = back_drawn // 2
    back_partial_top_gone = (back_drawn % 2) == 1

    # Determine, for each physical stack, whether it has been fully drawn from
    # either side, has just its top gone, or is fully present.
    present_flat: set[int] = set()
    for s in range(NUM_STACKS):
        # CW front: k_front = how many stacks CW from break this stack is.
        k_front = (break_stack - s) % NUM_STACKS
        # CCW back: k_back = how many stacks CCW from break+1 this stack is.
        k_back = (s - break_stack - 1) % NUM_STACKS

        # Is this stack already fully drawn by either side?
        if k_front < front_full_stacks:
            continue
        if k_back < back_full_stacks:
            continue

        # Was its top removed by either side?
        top_gone = (
            (k_front == front_full_stacks and front_partial_top_gone)
            or (k_back == back_full_stacks and back_partial_top_gone)
        )
        if top_gone:
            present_flat.add(s * 2 + 1)  # only the bottom remains
        else:
            present_flat.add(s * 2)
            present_flat.add(s * 2 + 1)

    # Next-front position (CW direction, top-first per stack).
    nf_stack = (break_stack - front_full_stacks) % NUM_STACKS
    nf_layer = 1 if front_partial_top_gone else 0
    nf = flat_to_position(nf_stack * 2 + nf_layer)

    # Next-back position (CCW direction, top-first per stack).
    nb_stack = (break_stack + 1 + back_full_stacks) % NUM_STACKS
    nb_layer = 1 if back_partial_top_gone else 0
    nb = flat_to_position(nb_stack * 2 + nb_layer)

    remaining_positions = []
    for f in sorted(present_flat):
        p = flat_to_position(f)
        remaining_positions.append([p.seat, p.stack, p.layer])

    return {
        "remaining": rem,
        "next_front_position": [nf.seat, nf.stack, nf.layer],
        "next_back_position": [nb.seat, nb.stack, nb.layer],
        "remaining_positions": remaining_positions,
    }


def _pending_claim_window(hand: Hand, viewer_seat: int) -> Optional[dict]:
    if hand.game.phase != TurnPhase.CLAIM_WINDOW:
        return None
    if viewer_seat == hand.game.last_discard_player:
        return None
    # During a robbing-kong window, only eligible robbers see a claim window.
    if hand.game._pending_gang_add is not None and viewer_seat not in hand.robbing_kong_pending:
        return None
    available = [a.value for a in hand.available_actions(viewer_seat)
                 if a in (AvailableAction.PENG, AvailableAction.CHI,
                          AvailableAction.GANG_OPEN, AvailableAction.HU,
                          AvailableAction.ROBBING_KONG_PASS)]
    chi_combos: list[list[int]] = []
    if AvailableAction.CHI in hand.available_actions(viewer_seat):
        viewer = hand.game.players[viewer_seat]
        tile = hand.game.last_discard
        chi_combos = [list(combo) for combo in viewer.can_chi(tile)]
    is_robbing_kong = (
        hand.game._pending_gang_add is not None
        and viewer_seat in hand.robbing_kong_pending
    )
    return {
        "discarder_seat": hand.game.last_discard_player,
        "tile": hand.game.last_discard,
        "your_options": available,
        "is_robbing_kong_window": is_robbing_kong,
        "chi_combos": chi_combos,
    }
