"""Socket.io event handlers for in-game actions."""
from __future__ import annotations

import asyncio
import sys
import time
from typing import Optional

from server.app import sio
from server.protocol import ClientEvent, ServerEvent, HandPhase
from server.room import Room
from server.serialize import build_state_update, _active_seat
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
    await _perform_roll_dice(room)


async def _perform_roll_dice(room: Room) -> None:
    """Roll dice, deal, resolve flowers. Can be called by human handler or bot."""
    s = room.session
    if not s:
        return
    hand = s.current_hand
    if not hand or hand.phase != HandPhase.PRE_DICE:
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
            # During a robbing-kong window, skip the co-hu check — only the
            # robbing seat fires; apply_claim handles the robbing-kong path.
            if hand.game._pending_gang_add is not None:
                hand.snapshot()
                hand.apply_claim(seat, "hu")
                await _settle_single_or_multi(room)
                return
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
    # Subterfuge has now opened a CLAIM_WINDOW with _pending_gang_add set.
    # Check who can actually rob.
    tile = hand.game.last_discard
    declarer = hand.game.last_discard_player
    eligible = [s for s in range(4) if s != declarer and hand.can_hu_on_tile(s, tile)]
    if not eligible:
        # No robbers possible — auto-complete the gang immediately.
        hand.close_claim_window_no_winner()
    else:
        hand.start_robbing_kong_window(eligible)
    await _broadcast_state(room)


@sio.on("robbing_kong_pass")
async def on_robbing_kong_pass(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    if hand.game._pending_gang_add is None: return
    seat = room.session.seats.index(player.player_id)
    if seat not in hand.robbing_kong_pending:
        return
    hand.snapshot()
    all_passed = hand.record_robbing_kong_pass(seat)
    if all_passed:
        # Everyone declined to rob — complete the gang.
        hand.close_claim_window_no_winner()
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
    # Undo is allowed for the undo_owner (may be a human whose turn it isn't,
    # if the active player is a bot).
    from server.serialize import _active_seat as _as
    active = _as(hand)
    bot_seats_set = set(room.bot_seats())
    undo_owner = active
    if active in bot_seats_set:
        for offset in range(1, 5):
            cand = (active + offset) % 4
            if cand not in bot_seats_set:
                undo_owner = cand
                break
        else:
            undo_owner = None
    if seat != undo_owner:
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
    bot_seats_set = set(room.bot_seats())
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
                bot_seats=frozenset(bot_seats_set),
            )
            await sio.emit(ServerEvent.STATE_UPDATE.value, payload, to=player.sid)
    await _maybe_schedule_bot_turn(room)


async def _settle_single_or_multi(room: Room) -> None:
    """For single-winner Hu / self-Hu / wall-exhaustion. Wraps the GameResult."""
    import sys
    s = room.session
    hand = s.current_hand
    gr = hand.game.result
    hr = build_hand_result_from_game(gr) if gr else None
    if hr is None:
        return
    hand.clear_snapshots()
    s.record_settlement(hr)
    print(
        f"[settle] winner={hr.winner_seat} winning_tile={hr.winning_tile} "
        f"is_self_draw={hr.is_self_draw} payments={hr.payments} "
        f"cumulative={s.cumulative_scores} seats={s.seats}",
        file=sys.stderr,
    )
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


async def _maybe_schedule_bot_turn(room: Room) -> None:
    """If the next-to-act seat is a bot, schedule a bot action after a 2s delay."""
    if not room.session or not room.session.current_hand:
        return
    hand = room.session.current_hand
    if hand.phase in (HandPhase.SETTLEMENT,):
        return

    active = _active_seat(hand)

    # PRE_DICE: bot dealer should auto-roll.
    if hand.phase == HandPhase.PRE_DICE and active == hand.dealer_seat and room.is_bot_seat(active):
        token = (hand, hand.phase)

        async def _bot_roll():
            await asyncio.sleep(2.0)
            if room.session is None or room.session.current_hand is not hand:
                return
            if hand.phase != HandPhase.PRE_DICE:
                return
            if (hand, hand.phase) != token:
                return
            await _perform_roll_dice(room)

        asyncio.create_task(_bot_roll())
        return

    # Claim-window bots (robbing-kong or normal): handle pending responses.
    if hand.game.phase == TurnPhase.CLAIM_WINDOW:
        # Robbing-kong window — handle bots still pending.
        if hand.game._pending_gang_add is not None:
            pending_bots = [s for s in hand.robbing_kong_pending if room.is_bot_seat(s)]
            for bot_seat in pending_bots:
                _schedule_robbing_kong_bot(room, hand, bot_seat)
            return
        # co-hu window — handle bots still pending.
        if hand.co_hu_active:
            pending_bots = [s for s in hand.co_hu_remaining if room.is_bot_seat(s)]
            for bot_seat in pending_bots:
                _schedule_co_hu_bot(room, hand, bot_seat)
            return

    if not room.is_bot_seat(active):
        return

    token = (hand, active, len(hand.event_log))

    async def _do_bot_turn():
        await asyncio.sleep(2.0)
        if room.session is None or room.session.current_hand is not hand:
            return
        if (hand, _active_seat(hand), len(hand.event_log)) != token:
            return
        await _execute_bot_action(room, active)

    asyncio.create_task(_do_bot_turn())


def _schedule_robbing_kong_bot(room: Room, hand, bot_seat: int) -> None:
    """Schedule a bot's robbing-kong pass (bots never rob for simplicity)."""
    token = (hand, len(hand.event_log), bot_seat)

    async def _do():
        await asyncio.sleep(2.0)
        if room.session is None or room.session.current_hand is not hand:
            return
        if (hand, len(hand.event_log), bot_seat) != token:
            return
        if bot_seat not in hand.robbing_kong_pending:
            return
        hand.snapshot()
        all_passed = hand.record_robbing_kong_pass(bot_seat)
        if all_passed:
            hand.close_claim_window_no_winner()
        await _broadcast_state(room)

    asyncio.create_task(_do())


def _schedule_co_hu_bot(room: Room, hand, bot_seat: int) -> None:
    """Schedule a bot's co-hu response. Bot always passes (declines)."""
    token = (hand, len(hand.event_log), bot_seat)

    async def _do():
        await asyncio.sleep(2.0)
        if room.session is None or room.session.current_hand is not hand:
            return
        if (hand, len(hand.event_log), bot_seat) != token:
            return
        if not hand.co_hu_active or bot_seat not in hand.co_hu_remaining:
            return
        hand.snapshot()
        hand.record_co_hu_response(bot_seat, accept=False)
        if hand.co_hu_complete():
            await _finalize_co_hu(room)
        else:
            await _broadcast_state(room)

    asyncio.create_task(_do())


async def _execute_bot_action(room: Room, seat: int) -> None:
    """Run one bot action turn: query model, apply action, broadcast."""
    s = room.session
    if not s:
        return
    hand = s.current_hand
    if hand is None:
        return

    from subterfuge.env.action_space import index_to_action
    from subterfuge.types import ActionType
    from server.bot import choose_action_index

    try:
        idx = choose_action_index(hand.game, seat)
        action = index_to_action(idx, seat, hand.game)
    except Exception as e:
        print(f"[bot] seat={seat} error choosing action: {e}", file=sys.stderr)
        return

    hand.snapshot()
    atype = action.action_type

    try:
        if atype == ActionType.DRAW:
            # Subterfuge returns a DRAW action; pick front vs back based on state.
            if hand.game.phase == TurnPhase.CLAIM_WINDOW:
                hand.close_claim_window_no_winner()
            if hand.must_draw_back:
                hand.draw_back()
            else:
                hand.draw_front()
            if hand.phase.value == "SETTLEMENT":
                await _settle_single_or_multi(room)
                return
        elif atype == ActionType.DISCARD:
            hand.apply_discard(action.tile)
            LAST_DISCARD_TIME[room.code] = time.monotonic()
        elif atype == ActionType.CHI:
            # chi_tiles is the two tiles from hand; reconstruct from the meld.
            chi_hand_tiles = None
            if action.meld is not None:
                chi_hand_tiles = [t for t in action.meld.tiles if t != action.tile][:2]
            elif action.chi_tiles is not None:
                chi_hand_tiles = list(action.chi_tiles)
            hand.apply_claim(seat, "chi", tiles=chi_hand_tiles)
        elif atype == ActionType.PENG:
            hand.apply_claim(seat, "peng")
        elif atype == ActionType.GANG_CALL:
            hand.apply_claim(seat, "gang_open")
            hand.must_draw_back = True
        elif atype == ActionType.GANG_SELF:
            hand.declare_concealed_gang(action.tile)
        elif atype == ActionType.GANG_ADD:
            hand.declare_added_gang(action.tile)
            tile = hand.game.last_discard
            declarer = hand.game.last_discard_player
            eligible = [s2 for s2 in range(4) if s2 != declarer and hand.can_hu_on_tile(s2, tile)]
            if not eligible:
                hand.close_claim_window_no_winner()
            else:
                hand.start_robbing_kong_window(eligible)
        elif atype == ActionType.HU:
            if hand.game.phase == TurnPhase.CLAIM_WINDOW:
                # Check for co-hu (other human can also hu).
                others = []
                tile = hand.game.last_discard
                discarder = hand.game.last_discard_player
                for s2 in range(4):
                    if s2 == seat or s2 == discarder:
                        continue
                    if hand.can_hu_on_tile(s2, tile):
                        others.append(s2)
                if others:
                    hand.start_co_hu_window(seat)
                    await _broadcast_state(room)
                    return
                hand.apply_claim(seat, "hu")
            else:
                hand.declare_self_hu()
            if hand.phase.value == "SETTLEMENT":
                await _settle_single_or_multi(room)
                return
        elif atype == ActionType.PASS:
            # During a normal claim window, the next-to-draw seat treats PASS
            # as "close window + draw" — otherwise the bot is stuck because
            # no one is going to advance the turn.
            if (
                hand.game.phase == TurnPhase.CLAIM_WINDOW
                and hand.game._pending_gang_add is None
                and not hand.co_hu_active
                and hand.game.last_discard_player is not None
                and seat == (hand.game.last_discard_player + 1) % 4
            ):
                hand.close_claim_window_no_winner()
                if hand.game.phase == TurnPhase.DRAW and not hand.must_draw_back:
                    hand.draw_front()
                    if hand.phase.value == "SETTLEMENT":
                        await _settle_single_or_multi(room)
                        return
            # Otherwise nothing to do — the bot is a non-next-to-draw
            # non-discarder during a claim window; just stays passed.
        else:
            # Unknown action type — do nothing.
            print(f"[bot] seat={seat} unknown action type {atype}", file=sys.stderr)
    except Exception as e:
        print(f"[bot] seat={seat} error executing action {atype}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

    await _broadcast_state(room)


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
