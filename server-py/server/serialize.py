"""Build per-player state_update JSON dicts."""
from __future__ import annotations

from typing import Optional

from subterfuge.tiles import is_flower
from subterfuge.types import Wind, TurnPhase

from server.hand import Hand
from server.protocol import HandPhase, AvailableAction
from server.wall_view import flat_to_position, TILES_PER_SEAT, TOTAL_WALL_TILES

WIND_NAMES = ["EAST", "SOUTH", "WEST", "NORTH"]


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
        "drawn_tile": you_player._just_drew,
        "score": cumulative_scores[viewer_seat],
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
            "melds": [_meld_dict(m) for m in op.melds],
            "flowers": list(op.flowers),
            "discards": list(op.discards),
            "score": cumulative_scores[s],
        })

    wall = _wall_payload(hand)
    pending = _pending_claim_window(hand, viewer_seat)
    available = [a.value for a in hand.available_actions(viewer_seat)]

    return {
        "phase": hand.phase.value,
        "round_wind": WIND_NAMES[round_wind_index],
        "dealer_seat": hand.dealer_seat,
        "dealer_streak": dealer_streak,
        "current_turn_seat": hand.game.current_player,
        "you": you,
        "others": others,
        "wall": wall,
        "available_actions": available,
        "pending_claim_window": pending,
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


def _wall_payload(hand: Hand) -> dict:
    wall = hand.game.wall
    front_idx = wall._front
    back_idx = wall._back
    rem = max(0, back_idx - front_idx + 1)
    offset = hand.wall_rotation_offset
    physical_front = (front_idx + offset) % TOTAL_WALL_TILES if 0 <= front_idx < TOTAL_WALL_TILES else None
    physical_back = (back_idx + offset) % TOTAL_WALL_TILES if 0 <= back_idx < TOTAL_WALL_TILES else None
    nf = flat_to_position(physical_front) if physical_front is not None else None
    nb = flat_to_position(physical_back) if physical_back is not None else None
    return {
        "remaining": rem,
        "next_front_position": [nf.seat, nf.stack, nf.layer] if nf else None,
        "next_back_position": [nb.seat, nb.stack, nb.layer] if nb else None,
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
    }
