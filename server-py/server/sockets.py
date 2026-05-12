"""Socket.io event handlers for in-game actions."""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from server.app import sio
from server.protocol import ClientEvent, ServerEvent, HandPhase
from server.room import Room
from server.serialize import build_state_update
from server.session import build_hand_result_from_game
from subterfuge.types import TurnPhase, Wind


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
    if player is None:
        return
    if room.session is None:
        # Lobby phase — drop the player and notify remaining lobby viewers.
        room.remove_player(player_id)
        remaining = Room.get(code)
        if remaining is not None:
            await sio.emit(ServerEvent.LOBBY_UPDATE.value, {
                "players": [p.username for p in remaining.players],
                "leader": remaining.leader.username if remaining.leader else None,
            }, room=code)
    else:
        # In-game — keep the player record so they can reconnect with same player_id.
        player.sid = None


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
    # Stream dealing animation events with a small delay so the deal feels animated.
    DEAL_STEP_DELAY = 0.2  # seconds between batches of 4 tiles
    order = [(hand.dealer_seat + i) % 4 for i in range(4)]
    for _ in range(4):
        for s in order:
            await sio.emit(ServerEvent.DEALING_STEP.value, {"seat": s, "count": 4}, room=room.code)
            await asyncio.sleep(DEAL_STEP_DELAY)
    await sio.emit(ServerEvent.DEALING_STEP.value, {"seat": hand.dealer_seat, "count": 1}, room=room.code)
    await asyncio.sleep(DEAL_STEP_DELAY)
    await _broadcast_state(room)

    # Auto-resolve flowers from the initial deal.
    # Rule: each player drains ALL their currently-pending flowers in their
    # turn (drawing all replacements); any replacement that's itself a flower
    # waits for the NEXT round. Continue rounds until nobody has pending.
    FLOWER_STEP_DELAY = 0.4
    while hand.has_any_pending_flowers():
        for offset in range(4):
            seat = (hand.dealer_seat + offset) % 4
            steps = hand.auto_resolve_round_for_seat(seat)
            if not steps:
                continue
            for step in steps:
                await sio.emit("flower_resolved", {**step, "seat": seat}, room=room.code)
                await _broadcast_state(room)
                special = hand.check_special_flower_win()
                if special is not None:
                    await _settle_flower_special_win(room, hand, special)
                    return
                if hand.phase == HandPhase.SETTLEMENT:  # wall exhausted
                    await _settle_single_or_multi(room)
                    return
                await asyncio.sleep(FLOWER_STEP_DELAY)
    hand.enter_playing()
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
    expected_seat = hand.game.current_player
    if hand.game.phase.name == "CLAIM_WINDOW" and hand.game.last_discard_player is not None:
        expected_seat = (hand.game.last_discard_player + 1) % 4
    if seat != expected_seat:
        return
    hand.snapshot()
    if hand.game.phase.name == "CLAIM_WINDOW":
        hand.close_claim_window_no_winner()
    hand.draw_front()
    if hand.phase.value == "SETTLEMENT":
        await _settle_single_or_multi(room)
    else:
        await _broadcast_state(room)


@sio.on(ClientEvent.DRAW_BACK.value)
async def on_draw_back(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    if seat != hand.game.current_player:
        return
    hand.snapshot()
    hand.draw_back()
    if hand.phase.value == "SETTLEMENT":
        await _settle_single_or_multi(room)
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


@sio.on(ClientEvent.CLAIM.value)
async def on_claim(sid: str, data: dict) -> None:
    import sys, traceback
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    try:
        if data["action"] == "hu":
            # Detect if multiple players can hu on this tile.
            others = []
            if hand.game.phase.name == "CLAIM_WINDOW":
                tile = hand.game.last_discard
                discarder = hand.game.last_discard_player
                for s in range(4):
                    if s == seat or s == discarder:
                        continue
                    if hand.can_hu_on_tile(s, tile):
                        others.append(s)
            if others:
                # Co-hu window — pause for other eligible seats to respond.
                hand.snapshot()
                hand.start_co_hu_window(seat)
                await _broadcast_state(room)
                return
            # Single-winner — proceed as before.
            hand.snapshot()
            hand.apply_claim(seat, "hu")
            await _settle_single_or_multi(room)
            return
        hand.snapshot()
        hand.apply_claim(seat, data["action"], tiles=data.get("tiles"))
        await _broadcast_state(room)
    except Exception as e:
        print(f"[on_claim] action={data.get('action')} tiles={data.get('tiles')} seat={seat} error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # Re-broadcast current state so the client doesn't get stuck.
        await _broadcast_state(room)


@sio.on(ClientEvent.CO_HU_RESPONSE.value)
async def on_co_hu_response(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand or not hand.co_hu_active: return
    seat = room.session.seats.index(player.player_id)
    if seat not in hand.co_hu_remaining: return
    accept = bool(data.get("accept", False))
    hand.snapshot()
    hand.record_co_hu_response(seat, accept)
    if hand.co_hu_complete():
        await _finalize_co_hu(room)
    else:
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
    await _settle_single_or_multi(room)


@sio.on(ClientEvent.UNDO.value)
async def on_undo(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    expected_seat = hand.game.current_player
    if hand.game.phase.name == "CLAIM_WINDOW" and hand.game.last_discard_player is not None:
        expected_seat = (hand.game.last_discard_player + 1) % 4
    if seat != expected_seat:
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


async def _settle_single_or_multi(room: Room) -> None:
    """For single-winner Hu / self-Hu / wall-exhaustion. Wraps the GameResult."""
    s = room.session
    hand = s.current_hand
    gr = hand.game.result
    hr = build_hand_result_from_game(gr) if gr else None
    if hr is None:
        return
    hand.clear_snapshots()
    s.record_settlement(hr)
    await sio.emit(ServerEvent.HAND_SETTLEMENT.value, {
        "winners": [
            {
                "seat": hr.winner_seat,
                "winning_tile": hr.winning_tile,
                "breakdown": hr.breakdown,
                "total": hr.total,
            }
        ] if hr.winner_seat is not None else [],
        "is_draw": hr.is_draw,
        "source": "self" if hr.is_self_draw else "discard",
        "payments": hr.payments,
        "cumulative": s.cumulative_scores,
        "next_dealer_seat": s.next_hand_dealer_seat(),
    }, room=room.code)
    # Broadcast updated state so the scoreboard reflects the new cumulative
    # scores while the settlement modal is shown.
    await _broadcast_state(room)


async def _settle_flower_special_win(room: Room, hand, special: tuple[int, int | None]) -> None:
    """Settle 八仙过海 / 七抢一 detected during flower resolution."""
    from subterfuge.engine.rulesets.dan_full import DAN_FULL_RULESET
    from subterfuge.engine.rulesets.base import ScoringContext, PaymentContext
    from subterfuge.types import GameResult, TurnPhase as _TP
    winner_seat, sole_payer = special
    p = hand.game.players[winner_seat]
    ctx = ScoringContext(
        hand=p.hand, declared_melds=p.melds, winning_tile=-1,
        is_self_draw=(sole_payer is None),
        seat_wind=p.seat_wind, round_wind=hand.game.config.round_wind,
        flowers=list(p.flowers), is_dealer=p.is_dealer,
        is_last_tile=False, is_robbing_kong=False, is_replacement_draw=False,
        is_first_draw=True, wall_remaining=hand.game.wall.remaining,
        dealer_streak=hand.dealer_streak,
        other_flowers=[
            list(hand.game.players[i].flowers) + list(hand.pending_flowers[i])
            if i != winner_seat else []
            for i in range(4)
        ],
    )
    tai, breakdown = DAN_FULL_RULESET.score(ctx)
    pay_ctx = PaymentContext(
        winner=winner_seat,
        discarder=sole_payer if sole_payer is not None else -1,
        is_self_draw=(sole_payer is None),
        dealer=hand.dealer_seat, dealer_streak=hand.dealer_streak,
        num_players=4, sole_payer=sole_payer,
    )
    payments = DAN_FULL_RULESET.settle(tai, breakdown, pay_ctx)
    hand.game.result = GameResult(
        winner=winner_seat, winning_tile=-1,
        is_self_draw=(sole_payer is None), is_robbing_kong=False,
        tai=tai, tai_breakdown=breakdown, payments=payments,
        discarder=sole_payer if sole_payer is not None else -1,
    )
    hand.phase = HandPhase.SETTLEMENT
    hand.game.phase = _TP.GAME_OVER
    await _settle_single_or_multi(room)


async def _finalize_co_hu(room: Room) -> None:
    """Run apply_multi_hu and emit a multi-winner hand_settlement."""
    s = room.session
    hand = s.current_hand
    results_gr = hand.finalize_co_hu()
    hand.clear_snapshots()
    hr_list = [build_hand_result_from_game(gr) for gr in results_gr]
    s.record_multi_settlement(hr_list)
    agg = [0, 0, 0, 0]
    for hr in hr_list:
        for i in range(4):
            agg[i] += hr.payments[i]
    await sio.emit(ServerEvent.HAND_SETTLEMENT.value, {
        "winners": [
            {
                "seat": hr.winner_seat,
                "winning_tile": hr.winning_tile,
                "breakdown": hr.breakdown,
                "total": hr.total,
            }
            for hr in hr_list
        ],
        "is_draw": False,
        "source": "discard",
        "payments": agg,
        "cumulative": s.cumulative_scores,
        "next_dealer_seat": s.next_hand_dealer_seat(),
    }, room=room.code)
    # Broadcast updated state so the scoreboard reflects the new cumulative
    # scores while the settlement modal is shown.
    await _broadcast_state(room)
