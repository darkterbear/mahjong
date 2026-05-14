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
    # If a claim window is open, drop silently — it manages its own resolution.
    if hand.claim_window is not None:
        return
    if hand.game.phase.name != "DRAW":
        return
    seat = room.session.seats.index(player.player_id)
    if seat != hand.game.current_player:
        return
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
    hand.apply_discard(data["tile_id"])
    hand.open_claim_window(discarder=seat, tile=data["tile_id"], is_robbing_kong=False)
    await _broadcast_state(room)
    await _start_claim_window_drivers(room)


@sio.on(ClientEvent.DECLARE_CONCEALED_GANG.value)
async def on_concealed_gang(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.declare_concealed_gang(data["tile_id"])
    await _broadcast_state(room)


@sio.on(ClientEvent.DECLARE_ADDED_GANG.value)
async def on_added_gang(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.declare_added_gang(data["tile_id"])
    # Subterfuge has now opened a CLAIM_WINDOW with _pending_gang_add set.
    tile = hand.game.last_discard
    declarer = hand.game.last_discard_player
    hand.open_claim_window(discarder=declarer, tile=tile, is_robbing_kong=True)
    await _broadcast_state(room)
    await _start_claim_window_drivers(room)


@sio.on(ClientEvent.DECLARE_SELF_HU.value)
async def on_self_hu(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    hand.declare_self_hu()
    await _settle_single_or_multi(room)


@sio.on(ClientEvent.NEXT_HAND.value)
async def on_next_hand(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    seat = room.session.seats.index(player.player_id)
    if seat != room.session.next_hand_dealer_seat():
        return
    room.session.start_new_hand()
    await _broadcast_state(room)


@sio.on(ClientEvent.CLAIM_DECISION.value)
async def on_claim_decision(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    if hand.claim_window is None or seat not in hand.claim_window.pending_seats:
        return
    action = data.get("action", "pass")
    if action == "pass":
        decision = {"action": "pass"}
    elif action in ("peng", "chi", "gang_open", "hu"):
        decision = {"action": action}
        if action == "chi" and data.get("tiles"):
            decision["tiles"] = list(data["tiles"])
    else:
        return
    hand.record_claim_decision(seat, decision)
    await _broadcast_state(room)
    if hand.claim_window_resolvable():
        await _resolve_claim_window(room)


@sio.on(ClientEvent.CLAIM_WAIT.value)
async def on_claim_wait(sid: str, data: dict) -> None:
    room, player = _ctx(sid)
    if not room or not room.session: return
    hand = room.session.current_hand
    if not hand: return
    seat = room.session.seats.index(player.player_id)
    if hand.claim_window is None or seat not in hand.claim_window.pending_seats:
        return
    wait = bool(data.get("wait", True))
    hand.record_wait_toggle(seat, wait)
    await _broadcast_state(room)
    if not wait and hand.claim_window_resolvable():
        await _resolve_claim_window(room)


# ---- Claim window driver helpers -------------------------------------------

async def _start_claim_window_drivers(room: Room) -> None:
    """Start bots, auto-pass timers, and the resolution watcher for the current claim window."""
    hand = room.session.current_hand
    if not hand or hand.claim_window is None:
        return
    cw = hand.claim_window
    # Bots: poll model immediately, record decision.
    for seat in list(cw.pending_seats):
        if not room.is_bot_seat(seat):
            continue
        decision = _bot_claim_decision(hand, seat)
        hand.record_claim_decision(seat, decision)
    # Every human is auto-passed at the 2s mark unless they explicitly
    # claimed or pressed Wait. (Humans with no eligible claim never see a
    # prompt — see serialize._pending_claim_window — they're auto-passed
    # purely server-side.)
    for seat in list(cw.pending_seats):
        if room.is_bot_seat(seat):
            continue
        asyncio.create_task(_auto_pass_after(room, hand, seat, 2.0))
    # Schedule resolution timer.
    asyncio.create_task(_resolve_claim_window_when_ready(room, hand))
    # Push updated state with bots' decisions already applied.
    await _broadcast_state(room)


def _human_has_claim(hand, seat: int) -> bool:
    """True if this human seat has any eligible claim on the pending discard."""
    cw = hand.claim_window
    if cw is None:
        return False
    actions = hand.available_actions(seat)
    if cw.is_robbing_kong:
        return any(a.value == "hu" for a in actions)
    return any(a.value in ("peng", "chi", "gang_open", "hu") for a in actions)


def _bot_claim_decision(hand, seat: int) -> dict:
    """Use the model to decide what the bot does in the current claim window."""
    from subterfuge.env.action_space import index_to_action
    from subterfuge.types import ActionType
    from server.bot import choose_action_index
    try:
        idx = choose_action_index(hand.game, seat)
        action = index_to_action(idx, seat, hand.game)
    except Exception:
        return {"action": "pass"}
    if action.action_type == ActionType.HU:
        return {"action": "hu"}
    if action.action_type == ActionType.PENG:
        return {"action": "peng"}
    if action.action_type == ActionType.GANG_CALL:
        return {"action": "gang_open"}
    if action.action_type == ActionType.CHI:
        chi_hand_tiles = None
        if action.meld is not None:
            chi_hand_tiles = [t for t in action.meld.tiles if t != action.tile][:2]
        elif action.chi_tiles is not None:
            chi_hand_tiles = list(action.chi_tiles)
        return {"action": "chi", "tiles": chi_hand_tiles}
    return {"action": "pass"}


async def _auto_pass_after(room: Room, hand, seat: int, delay: float) -> None:
    await asyncio.sleep(delay)
    if room.session is None or room.session.current_hand is not hand:
        return
    if hand.claim_window is None or seat not in hand.claim_window.pending_seats:
        return
    if seat in hand.claim_window.waiters:
        return  # they pressed Wait — skip auto-pass
    hand.record_claim_decision(seat, {"action": "pass"})
    await _broadcast_state(room)


async def _resolve_claim_window_when_ready(room: Room, hand) -> None:
    """Poll until the claim window is resolvable, then resolve it."""
    while True:
        if room.session is None or room.session.current_hand is not hand:
            return
        if hand.claim_window is None:
            return
        if hand.claim_window_resolvable():
            await _resolve_claim_window(room)
            return
        remaining = hand.claim_window_remaining_seconds()
        await asyncio.sleep(max(0.05, min(remaining, 0.2)))


async def _resolve_claim_window(room: Room) -> None:
    """Apply highest-priority claim, or auto-draw if no claims."""
    hand = room.session.current_hand
    if hand is None:
        return
    cw = hand.claim_window
    if cw is None:
        return

    priority = {"hu": 3, "peng": 2, "gang_open": 2, "chi": 1, "pass": 0}
    actionable = [
        (seat, d) for seat, d in cw.decisions.items()
        if d and d.get("action") and d["action"] != "pass"
    ]

    # Multi-winner hu: all hu decisions share same priority.
    hu_winners = [seat for seat, d in actionable if d["action"] == "hu"]
    if hu_winners:
        hand.close_claim_window()
        if len(hu_winners) == 1:
            hand.apply_claim(hu_winners[0], "hu")
            await _settle_single_or_multi(room)
            return
        # Multi-winner.
        await _emit_multi_winner_settlement(room, hu_winners)
        return

    actionable.sort(key=lambda x: priority.get(x[1]["action"], 0), reverse=True)
    if actionable:
        seat, dec = actionable[0]
        hand.close_claim_window()
        hand.apply_claim(seat, dec["action"], tiles=dec.get("tiles"))
        if hand.phase.value == "SETTLEMENT":
            await _settle_single_or_multi(room)
            return
        await _broadcast_state(room)
        # If the claimer used gang_open, they need a draw_back.
        await _maybe_schedule_bot_turn(room)
        return

    # No claims — close window, advance to next player's draw.
    hand.close_claim_window()
    if hand.game.phase.name == "CLAIM_WINDOW":
        from subterfuge.types import Action, ActionType
        claims = {
            i: Action(ActionType.PASS, player=i)
            for i in range(4)
            if i != hand.game.last_discard_player
        }
        was_robbing = cw.is_robbing_kong
        hand.game.resolve_claim_window(claims)
        if hand.game.phase.name == "DRAW" and was_robbing:
            hand.must_draw_back = True
    await _broadcast_state(room)
    await _auto_draw_for_next(room)


async def _auto_draw_for_next(room: Room) -> None:
    """Auto-draw for the next-to-draw seat (human or bot)."""
    hand = room.session.current_hand
    if hand is None:
        return
    if hand.game.phase.name != "DRAW":
        return
    seat = hand.game.current_player
    if room.is_bot_seat(seat):
        # Bot turn driver will handle this after broadcast.
        await _maybe_schedule_bot_turn(room)
        return
    # Human: auto-draw for them.
    if hand.must_draw_back:
        hand.draw_back()
    else:
        hand.draw_front()
    if hand.phase.value == "SETTLEMENT":
        await _settle_single_or_multi(room)
        return
    await _broadcast_state(room)


async def _emit_multi_winner_settlement(room: Room, winner_seats: list[int]) -> None:
    """Settle a multi-winner hu via apply_multi_hu."""
    hand = room.session.current_hand
    results_gr = hand.apply_multi_hu(winner_seats)
    s = room.session
    hr_list = [build_hand_result_from_game(gr) for gr in results_gr]
    s.record_multi_settlement(hr_list)
    agg = [0, 0, 0, 0]
    for hr in hr_list:
        for i in range(4):
            agg[i] += hr.payments[i]
    await sio.emit(ServerEvent.HAND_SETTLEMENT.value, {
        "winners": [
            {"seat": hr.winner_seat, "winning_tile": hr.winning_tile,
             "breakdown": hr.breakdown, "total": hr.total}
            for hr in hr_list
        ],
        "is_draw": False,
        "source": "discard",
        "payments": agg,
        "cumulative": s.cumulative_scores,
        "next_dealer_seat": s.next_hand_dealer_seat(),
    }, room=room.code)
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
    # Don't schedule bot turns during an open claim window —
    # _start_claim_window_drivers handles bot decisions immediately.
    if hand.claim_window is not None:
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

    atype = action.action_type

    try:
        if atype == ActionType.DRAW:
            if hand.must_draw_back:
                hand.draw_back()
            else:
                hand.draw_front()
            if hand.phase.value == "SETTLEMENT":
                await _settle_single_or_multi(room)
                return
        elif atype == ActionType.DISCARD:
            p = hand.game.players[seat]
            target = action.tile
            if target < 0 or target >= 34 or int(p.hand[target]) <= 0:
                # Fallback: model returned a tile not in hand. Pick first legal tile.
                fallback = next((t for t in range(34) if int(p.hand[t]) > 0), None)
                if fallback is None:
                    print(f"[bot] seat={seat} no legal discard tiles; aborting bot turn", file=sys.stderr)
                    return
                print(f"[bot] seat={seat} model picked invalid discard tile {target}, falling back to {fallback}", file=sys.stderr)
                target = fallback
            hand.apply_discard(target)
            hand.open_claim_window(discarder=seat, tile=target, is_robbing_kong=False)
            await _broadcast_state(room)
            await _start_claim_window_drivers(room)
            return
        elif atype == ActionType.GANG_SELF:
            hand.declare_concealed_gang(action.tile)
        elif atype == ActionType.GANG_ADD:
            hand.declare_added_gang(action.tile)
            tile = hand.game.last_discard
            declarer = hand.game.last_discard_player
            hand.open_claim_window(discarder=declarer, tile=tile, is_robbing_kong=True)
            await _broadcast_state(room)
            await _start_claim_window_drivers(room)
            return
        elif atype == ActionType.HU:
            # Self-draw hu (during DISCARD phase).
            hand.declare_self_hu()
            if hand.phase.value == "SETTLEMENT":
                await _settle_single_or_multi(room)
                return
        else:
            # PASS or anything unexpected — do nothing.
            print(f"[bot] seat={seat} unhandled action type {atype}", file=sys.stderr)
    except Exception as e:
        print(f"[bot] seat={seat} error executing action {atype}: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        # Critical: dump the bot's hand state so we can diagnose later.
        p = hand.game.players[seat]
        in_hand = [t for t in range(34) if int(p.hand[t]) > 0]
        print(f"[bot] seat={seat} hand_tiles={in_hand} melds={len(p.melds)} pending_flowers={hand.pending_flowers[seat]}", file=sys.stderr)
        # Don't broadcast (which would re-schedule us into the same error).
        return

    await _broadcast_state(room)
