"""Socket.io event handlers for in-game actions."""
from __future__ import annotations

import time
from typing import Optional

from server.app import sio
from server.protocol import ClientEvent, ServerEvent
from server.room import Room
from server.serialize import build_state_update
from server.session import build_hand_result_from_game


SID_TO_CONTEXT: dict[str, tuple[str, str]] = {}  # sid → (room_code, player_id)
LAST_DISCARD_TIME: dict[str, float] = {}         # room_code → monotonic timestamp


@sio.event
async def auth(sid: str, data: dict) -> None:
    code = data["code"]
    player_id = data["player_id"]
    room = Room.get(code)
    if room is None:
        return
    player = next((p for p in room.players if p.player_id == player_id), None)
    if player is None:
        return
    player.sid = sid
    SID_TO_CONTEXT[sid] = (code, player_id)
    await sio.enter_room(sid, code)
    if room.session and room.session.current_hand:
        await _broadcast_state(room)


@sio.event
async def disconnect(sid: str) -> None:
    ctx = SID_TO_CONTEXT.pop(sid, None)
    if ctx is None:
        return
    code, player_id = ctx
    room = Room.get(code)
    if room is None:
        return
    player = next((p for p in room.players if p.player_id == player_id), None)
    if player:
        player.sid = None
    # Don't kill the room — allow reconnect.


@sio.on(ClientEvent.ROLL_DICE.value)
async def on_roll_dice(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session:
        return
    hand = room.session.current_hand
    if not hand:
        hand = room.session.start_new_hand()
    seat = room.session.seats.index(player.player_id)
    if seat != hand.dealer_seat:
        return
    hand.snapshot()
    dice = hand.roll_dice()
    await sio.emit(ServerEvent.DICE_ROLLED.value, {
        "d1": dice.d1, "d2": dice.d2, "d3": dice.d3,
        "break_seat": dice.break_seat, "break_offset": dice.break_offset,
    }, room=room.code)
    hand.deal_initial_hands()
    # Stream dealing animation events.
    order = [(hand.dealer_seat + i) % 4 for i in range(4)]
    for _ in range(4):
        for s in order:
            await sio.emit(ServerEvent.DEALING_STEP.value, {"seat": s, "count": 4}, room=room.code)
    await sio.emit(ServerEvent.DEALING_STEP.value, {"seat": hand.dealer_seat, "count": 1}, room=room.code)
    await _broadcast_state(room)


@sio.on(ClientEvent.DRAW_FRONT.value)
async def on_draw_front(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    # 0.5s discard delay.
    last = LAST_DISCARD_TIME.get(room.code, 0.0)
    if time.monotonic() - last < 0.5:
        return  # silently drop
    seat = room.session.seats.index(player.player_id)
    if seat != hand.game.current_player:
        return
    hand.snapshot()
    if hand.game.phase.name == "CLAIM_WINDOW":
        hand.close_claim_window_no_winner()
    hand.draw_front()
    if hand.phase.value == "SETTLEMENT":
        await _settle(room, hand_result=None)
    else:
        await _broadcast_state(room)


@sio.on(ClientEvent.DRAW_BACK.value)
async def on_draw_back(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    if seat not in (hand.game.current_player, hand.flower_resolution_seat):
        return
    hand.snapshot()
    hand.draw_back()
    if hand.phase.value == "SETTLEMENT":
        await _settle(room, hand_result=None)
    else:
        await _broadcast_state(room)


@sio.on(ClientEvent.DISCARD.value)
async def on_discard(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    if seat != hand.game.current_player: return
    hand.snapshot()
    hand.apply_discard(data["tile_id"])
    LAST_DISCARD_TIME[room.code] = time.monotonic()
    await _broadcast_state(room)


@sio.on(ClientEvent.DECLARE_FLOWER.value)
async def on_declare_flower(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.snapshot()
    hand.declare_flower(data["tile_id"])
    await _broadcast_state(room)


@sio.on(ClientEvent.CLAIM.value)
async def on_claim(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    hand.snapshot()
    if data["action"] == "hu":
        hand.apply_claim(seat, "hu")
        await _settle(room, hand_result=None)
        return
    hand.apply_claim(seat, data["action"], tiles=data.get("tiles"))
    await _broadcast_state(room)


@sio.on(ClientEvent.DECLARE_CONCEALED_GANG.value)
async def on_concealed_gang(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.snapshot()
    hand.declare_concealed_gang(data["tile_id"])
    await _broadcast_state(room)


@sio.on(ClientEvent.DECLARE_ADDED_GANG.value)
async def on_added_gang(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.snapshot()
    hand.declare_added_gang(data["tile_id"])
    await _broadcast_state(room)


@sio.on(ClientEvent.DECLARE_SELF_HU.value)
async def on_self_hu(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.snapshot()
    hand.declare_self_hu()
    await _settle(room, hand_result=None)


@sio.on(ClientEvent.UNDO.value)
async def on_undo(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    if seat != hand.game.current_player:
        return
    try:
        hand.undo()
    except RuntimeError:
        return
    await _broadcast_state(room)


@sio.on(ClientEvent.NEXT_HAND.value)
async def on_next_hand(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    seat = room.session.seats.index(player.player_id)
    if seat != room.session.next_hand_dealer_seat():
        return
    room.session.start_new_hand()
    await _broadcast_state(room)


# ---- helpers ---------------------------------------------------------------

def _ctx(sid: str):
    info = SID_TO_CONTEXT.get(sid)
    if not info:
        return None, None
    code, pid = info
    room = Room.get(code)
    if not room:
        return None, None
    player = next((p for p in room.players if p.player_id == pid), None)
    return room, player


async def _broadcast_state(room: Room) -> None:
    s = room.session
    if not s or not s.current_hand:
        return
    seats_usernames = []
    for pid in s.seats:
        match = next((p.username for p in room.players if p.player_id == pid), "?")
        seats_usernames.append(match)
    for seat_idx, pid in enumerate(s.seats):
        player = next((p for p in room.players if p.player_id == pid), None)
        if player and player.sid:
            payload = build_state_update(
                hand=s.current_hand,
                viewer_seat=seat_idx,
                seats=seats_usernames,
                cumulative_scores=s.cumulative_scores,
                round_wind_index=s.round_wind_index,
                dealer_streak=s.dealer_streak,
            )
            await sio.emit(ServerEvent.STATE_UPDATE.value, payload, to=player.sid)


async def _settle(room: Room, hand_result) -> None:
    s = room.session
    hand = s.current_hand
    gr = hand.game.result
    hr = build_hand_result_from_game(gr) if gr else None
    if hr is None:
        return
    hand.clear_snapshots()
    s.record_settlement(hr)
    await sio.emit(ServerEvent.HAND_SETTLEMENT.value, {
        "winner_seat": hr.winner_seat,
        "winning_tile": hr.winning_tile,
        "source": "self" if hr.is_self_draw else "discard",
        "breakdown": hr.breakdown,
        "total": hr.total,
        "payments": hr.payments,
        "cumulative": s.cumulative_scores,
        "next_dealer_seat": s.next_hand_dealer_seat(),
    }, room=room.code)
