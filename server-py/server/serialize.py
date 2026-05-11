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

    # Build the set of physical flat indices STILL present in the wall.
    # A stack is identified by (logical_flat // 2). It has 2 layers:
    #   layer 0 (top)    = logical flat index 2*s
    #   layer 1 (bottom) = logical flat index 2*s + 1
    #
    # Front draws remove tiles in flat order (0, 1, 2, ...) — already top-first.
    # Back draws remove tiles from the end (143, 142, ...) — currently bottom-first,
    # but we want to report positions TOP-FIRST per stack from the back end.
    #
    # "Back-drawn" means: back_drawn tiles have been taken from the back.
    # Physical back index is back_drawn; in stack terms:
    #   back_full_stacks = back_drawn // 2   (fully removed stacks from the end)
    #   back_partial_top_gone = (back_drawn % 2) == 1  (one extra draw: bottom gone first,
    #     but since we're reporting top-first, if bottom was drawn the top was drawn first)
    #
    # Wait — subterfuge removes bottom (flat 2s+1) BEFORE top (flat 2s) from the back.
    # But for our visual representation we want to SHOW top-first removal.
    # The remapping: actual draw from flat `143-k` maps to visual top-first ordering,
    # where we show the top of the last stack gone first.
    #
    # For remaining_positions: a position is present if not yet drawn from either end.
    # We track this by the flat index range [front_drawn .. total-1-back_drawn].

    half_total = total // 2  # 72 stacks

    # Stacks fully drawn from front: stacks 0 .. front_full_stacks-1
    front_full_stacks = front_drawn // 2
    front_partial_top_gone = (front_drawn % 2) == 1  # stack front_full_stacks: top drawn, bottom remains

    # Stacks fully drawn from back (top-first per stack):
    # Each back draw takes the TOP of the current back stack, then its BOTTOM.
    back_full_stacks = back_drawn // 2
    back_partial_top_gone = (back_drawn % 2) == 1  # back stack: top drawn, bottom remains

    present_flat: set[int] = set()
    for s in range(half_total):
        # Front side: skip stacks fully consumed from front.
        if s < front_full_stacks:
            continue  # fully drawn from front
        if s == front_full_stacks and front_partial_top_gone:
            # Top (layer 0) already drawn; only bottom (layer 1) remains.
            physical = (offset + 2 * s + 1) % total
            present_flat.add(physical)
            continue

        # Back side: stacks from the end.
        from_end = half_total - 1 - s
        if from_end < back_full_stacks:
            continue  # fully drawn from back
        if from_end == back_full_stacks and back_partial_top_gone:
            # TOP already drawn from back; only bottom remains.
            physical = (offset + 2 * s + 1) % total
            present_flat.add(physical)
            continue

        # Both layers present.
        present_flat.add((offset + 2 * s) % total)
        present_flat.add((offset + 2 * s + 1) % total)

    remaining_positions = []
    for f in sorted(present_flat):
        p = flat_to_position(f)
        remaining_positions.append([p.seat, p.stack, p.layer])

    # Next-front position: top of the next front stack (or bottom if top already gone).
    if front_partial_top_gone and front_full_stacks < half_total:
        next_front_flat = (offset + 2 * front_full_stacks + 1) % total
    else:
        next_front_flat = (offset + 2 * front_full_stacks) % total
    nf = flat_to_position(next_front_flat)

    # Next-back position: TOP of the current back stack first, then BOTTOM.
    back_s = half_total - 1 - back_full_stacks
    if back_s < 0:
        nb = None
    elif back_partial_top_gone:
        # TOP already gone; next draw takes the BOTTOM.
        next_back_flat = (offset + 2 * back_s + 1) % total
        nb = flat_to_position(next_back_flat)
    else:
        # TOP is next.
        next_back_flat = (offset + 2 * back_s) % total
        nb = flat_to_position(next_back_flat)

    return {
        "remaining": rem,
        "next_front_position": [nf.seat, nf.stack, nf.layer] if nf else None,
        "next_back_position": [nb.seat, nb.stack, nb.layer] if nb else None,
        "remaining_positions": remaining_positions,
    }


def _pending_claim_window(hand: Hand, viewer_seat: int) -> Optional[dict]:
    if hand.game.phase != TurnPhase.CLAIM_WINDOW:
        return None
    if viewer_seat == hand.game.last_discard_player:
        return None
    available = [a.value for a in hand.available_actions(viewer_seat)
                 if a in (AvailableAction.PENG, AvailableAction.CHI,
                          AvailableAction.GANG_OPEN, AvailableAction.HU)]
    return {
        "discarder_seat": hand.game.last_discard_player,
        "tile": hand.game.last_discard,
        "your_options": available,
        "is_robbing_kong_window": hand.game._pending_gang_add is not None,
    }
