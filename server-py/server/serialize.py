"""Build per-player state_update JSON dicts."""
from __future__ import annotations

from typing import Optional

from subterfuge.tiles import is_flower
from subterfuge.types import Wind, TurnPhase

from server.hand import Hand
from server.protocol import HandPhase, AvailableAction
from server.wall_view import flat_to_position, TILES_PER_SEAT, TOTAL_WALL_TILES

WIND_NAMES = ["EAST", "SOUTH", "WEST", "NORTH"]


_PRIVATE_TILE_KINDS = {"draw_front", "draw_back", "gang_concealed"}


def _redact_event_log(event_log: list[dict], viewer_seat: int) -> list[dict]:
    """Hide tile ids that should be private to other players (draws + concealed gangs)."""
    out: list[dict] = []
    for e in event_log:
        if e.get("kind") in _PRIVATE_TILE_KINDS and e.get("seat") != viewer_seat:
            out.append({k: v for k, v in e.items() if k != "tile"})
        else:
            out.append(dict(e))
    return out


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
    bot_seats: frozenset[int] = frozenset(),
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

    # Once the hand is settled, every winner's hidden tiles are revealed to
    # all viewers (so opponents can see how the win was constructed).
    is_settled = hand.phase == HandPhase.SETTLEMENT
    winner_seats = set(hand.winner_seats) if is_settled else set()

    others = []
    for offset in range(1, 4):
        s = (viewer_seat + offset) % 4
        op = hand.game.players[s]
        other_entry = {
            "seat": s,
            "seat_wind": _seat_wind_name(s, hand.dealer_seat),
            "username": seats[s],
            "hand_count": int(op.hand.sum()) + len(hand.pending_flowers[s]),
            "pending_flowers": list(hand.pending_flowers[s]),
            # Concealed gangs stay hidden during play and are revealed once
            # the hand has settled.
            "melds": [
                _meld_dict(m, hide_concealed=not is_settled) for m in op.melds
            ],
            "flowers": list(op.flowers),
            "discards": list(op.discards),
            "score": cumulative_scores[s],
        }
        if s in winner_seats:
            other_entry["hand"] = _hand_as_list(op.hand) + list(hand.pending_flowers[s])
        others.append(other_entry)

    wall = _wall_payload(hand)
    pending = _pending_claim_window(hand, viewer_seat, seats)
    available = [a.value for a in hand.available_actions(viewer_seat)]

    # The just-discarded tile sitting in the claim window, visible to every
    # viewer (including the discarder and players with no eligible claim).
    # Drives the "big tile under the discard grid" indicator on the client.
    active_discard = None
    if hand.claim_window is not None and not hand.claim_window.is_robbing_kong:
        active_discard = {
            "tile": hand.claim_window.tile,
            "discarder_seat": hand.claim_window.discarder,
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
        "active_discard": active_discard,
        "event_log": _redact_event_log(hand.event_log, viewer_seat),
    }


def _hand_as_list(hand_counts) -> list[int]:
    out = []
    for tid in range(len(hand_counts)):
        out.extend([tid] * int(hand_counts[tid]))
    return out


def _meld_dict(meld, *, hide_concealed: bool = False) -> dict:
    """Build the meld payload for a viewer.

    `hide_concealed`: when True, GANG_CONCEALED melds have their tiles
    replaced with placeholders so opposing viewers can't read the tile id
    during play. Once the hand settles, set this to False to reveal.
    """
    is_concealed_gang = meld.meld_type.name == "GANG_CONCEALED"
    if hide_concealed and is_concealed_gang:
        return {
            "type": meld.meld_type.name,
            "tiles": [-1, -1, -1, -1],
            "concealed_hidden": True,
            "source_seat": meld.source_player,
            "source_tile": None,
        }
    return {
        "type": meld.meld_type.name,
        "tiles": list(meld.tiles),
        "source_seat": meld.source_player,
        "source_tile": getattr(meld, "source_tile", None),
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


def _pending_claim_window(hand: Hand, viewer_seat: int, seats: list[str] | None = None) -> Optional[dict]:
    cw = hand.claim_window
    if cw is None:
        return None
    if viewer_seat == cw.discarder:
        return None

    # your_options: from available_actions filtered to claim types.
    your_options = []
    if viewer_seat in cw.pending_seats:
        for a in hand.available_actions(viewer_seat):
            if a.value in ("hu", "peng", "chi", "gang_open"):
                your_options.append(a.value)

    # If the viewer has nothing to do (no eligible claims), hide the claim
    # window from them entirely — they don't get prompted, the server
    # auto-passes them at the 2s mark.
    if not your_options and viewer_seat in cw.pending_seats:
        return None

    chi_combos: list[list[int]] = []
    if "chi" in your_options:
        chi_combos = [list(c) for c in hand.game.players[viewer_seat].can_chi(cw.tile)]

    you_decided = viewer_seat not in cw.pending_seats
    you_waiting = viewer_seat in cw.waiters
    you_no_timer = viewer_seat in cw.auto_waiters
    waiters_list = sorted(cw.waiters)

    waiter_usernames: list[str] = []
    if seats is not None:
        waiter_usernames = [seats[s] for s in waiters_list]

    return {
        "discarder_seat": cw.discarder,
        "tile": cw.tile,
        "is_robbing_kong_window": cw.is_robbing_kong,
        "your_options": your_options,
        "chi_combos": chi_combos,
        "you_decided": you_decided,
        "you_waiting": you_waiting,
        "you_no_timer": you_no_timer,
        "waiters": waiters_list,
        "waiter_usernames": waiter_usernames,
        "remaining_seconds": 0.0 if you_waiting else hand.claim_window_remaining_seconds(),
    }
