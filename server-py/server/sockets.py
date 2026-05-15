"""Socket.io event handlers for in-game actions."""
from __future__ import annotations

import asyncio
import sys
import time
import traceback
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
    # Replacement draw is mandatory — auto-pull from the back rather than
    # prompting the player for a separate confirmation.
    if hand.must_draw_back:
        hand.draw_back()
        if hand.phase.value == "SETTLEMENT":
            await _settle_single_or_multi(room)
            return
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
    # Idempotency: if the previous hand is already settled and a new Hand
    # has been started (perhaps by the bot auto-advance task firing first),
    # don't start a second one. The hand object is replaced atomically by
    # start_new_hand; we only advance when the current hand is still in
    # SETTLEMENT.
    current = room.session.current_hand
    if current is None or current.phase != HandPhase.SETTLEMENT:
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
    elif action in ("peng", "gang_open", "hu"):
        decision = {"action": action}
    elif action == "chi":
        # Chi requires exactly two integer hand tiles. Reject anything else
        # so a malformed message can't crash _resolve_claim_window with an
        # AssertionError and hang the room.
        tiles = data.get("tiles")
        if (
            not isinstance(tiles, list)
            or len(tiles) != 2
            or not all(isinstance(t, int) and 0 <= t < 34 for t in tiles)
        ):
            print(
                f"[claim] seat={seat} rejected malformed chi decision tiles={tiles!r}",
                file=sys.stderr,
            )
            return
        decision = {"action": "chi", "tiles": list(tiles)}
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
    # Humans with HU as an option auto-enter Wait so they get unbounded
    # time to consider a winning hand without being force-passed at 2s.
    from server.protocol import AvailableAction
    for seat in list(cw.pending_seats):
        if room.is_bot_seat(seat):
            continue
        if AvailableAction.HU in hand.available_actions(seat):
            cw.waiters.add(seat)
    # Every human (or remaining bot, defense-in-depth) is auto-passed at
    # the 2s mark unless they explicitly claimed, pressed Wait, or were
    # auto-waited above. The auto-pass task loops while the seat is in
    # waiters, so it'll fire if/when they stop waiting without deciding.
    for seat in list(cw.pending_seats):
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
    """Auto-pass *seat* once the grace window has elapsed AND they're not waiting.

    Waits `delay` seconds first, then polls while the player is in waiters so
    that releasing Wait (or cancelling out of the chi picker) still triggers
    the auto-pass — otherwise the seat would sit in pending forever.
    """
    try:
        await asyncio.sleep(delay)
        while True:
            if room.session is None or room.session.current_hand is not hand:
                return
            if hand.claim_window is None or seat not in hand.claim_window.pending_seats:
                return
            if seat not in hand.claim_window.waiters:
                hand.record_claim_decision(seat, {"action": "pass"})
                await _broadcast_state(room)
                return
            await asyncio.sleep(0.2)
    except Exception as e:
        print(f"[claim] auto_pass_after seat={seat} crashed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


async def _resolve_claim_window_when_ready(room: Room, hand) -> None:
    """Poll until the claim window is resolvable, then resolve it.

    Force-passes any NON-waiter seats that have been stuck in pending
    past the safety timeout — covers silent bot crashes or any
    auto_pass_after task that died. Waiters (humans who pressed Wait
    or opened the chi picker) are NEVER force-passed; they get
    unbounded time to decide. If they want to release the window they
    must explicitly Stop Waiting or pick an action.
    """
    NON_WAITER_TIMEOUT = 15.0
    forced_non_waiters = False
    try:
        while True:
            if room.session is None or room.session.current_hand is not hand:
                return
            cw = hand.claim_window
            if cw is None:
                return
            if hand.claim_window_resolvable():
                await _resolve_claim_window(room)
                return
            elapsed = time.monotonic() - cw.started_at
            if (
                not forced_non_waiters
                and elapsed >= NON_WAITER_TIMEOUT
            ):
                non_waiters = list(cw.pending_seats - cw.waiters)
                if non_waiters:
                    print(
                        f"[claim] safety-net force-pass non-waiters "
                        f"after {elapsed:.1f}s: {sorted(non_waiters)} "
                        f"(waiters still active={sorted(cw.waiters)})",
                        file=sys.stderr,
                    )
                    for s in non_waiters:
                        hand.record_claim_decision(s, {"action": "pass"})
                    await _broadcast_state(room)
                forced_non_waiters = True
                continue
            remaining = hand.claim_window_remaining_seconds()
            await asyncio.sleep(max(0.05, min(remaining, 0.2)))
    except Exception as e:
        print(f"[claim] resolve poll crashed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


async def _resolve_claim_window(room: Room) -> None:
    """Apply highest-priority claim, or auto-draw if no claims.

    Wrapped in a top-level try/except so a malformed claim payload (e.g.
    chi with bad tiles → ValueError) cleans up the window instead of
    leaving it stuck open with the polling task forever waiting on a
    state that will never become resolvable.
    """
    hand = room.session.current_hand
    if hand is None:
        return
    cw = hand.claim_window
    if cw is None:
        return

    try:
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
            # After gang_open the claimer owes a replacement draw. Auto-draw it
            # (for both humans and bots) so nobody has to click "Draw (back)".
            if hand.must_draw_back:
                if room.is_bot_seat(seat):
                    await _maybe_schedule_bot_turn(room)
                else:
                    hand.draw_back()
                    if hand.phase.value == "SETTLEMENT":
                        await _settle_single_or_multi(room)
                        return
                    await _broadcast_state(room)
            else:
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
    except Exception as e:
        print(f"[claim] _resolve_claim_window crashed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # Bail out cleanly — close any half-open window and broadcast so the
        # next bot turn can be scheduled. The game state may now be wedged,
        # but at least the room isn't permanently frozen.
        try:
            hand.close_claim_window()
            await _broadcast_state(room)
            if hand.game.phase.name == "DRAW":
                await _auto_draw_for_next(room)
        except Exception as cleanup_err:
            print(f"[claim] cleanup also failed: {cleanup_err}", file=sys.stderr)


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
    discarder_seat = next((hr.discarder_seat for hr in hr_list if hr.discarder_seat is not None), None)
    next_dealer = s.next_hand_dealer_seat()
    auto_advance = 10.0 if room.is_bot_seat(next_dealer) else None
    await sio.emit(ServerEvent.HAND_SETTLEMENT.value, {
        "winners": [
            {"seat": hr.winner_seat, "winning_tile": hr.winning_tile,
             "breakdown": hr.breakdown, "total": hr.total}
            for hr in hr_list
        ],
        "is_draw": False,
        "source": "discard",
        "discarder_seat": discarder_seat,
        "payments": agg,
        "cumulative": s.cumulative_scores,
        "next_dealer_seat": next_dealer,
        "auto_advance_seconds": auto_advance,
    }, room=room.code)
    await _broadcast_state(room)
    if auto_advance is not None:
        await _schedule_next_hand_auto_advance(room, auto_advance)


async def _schedule_next_hand_auto_advance(room: Room, delay: float) -> None:
    """If the next dealer is a bot, advance to the next hand after `delay` seconds.

    Snapshots the current Hand so a manual advance (or another settlement)
    in the meantime cancels this one without firing.
    """
    if room.session is None or room.session.current_hand is None:
        return
    hand_token = room.session.current_hand

    async def _advance():
        await asyncio.sleep(delay)
        if room.session is None or room.session.current_hand is not hand_token:
            return
        # Confirm still in SETTLEMENT and the dealer is still a bot.
        if hand_token.phase != HandPhase.SETTLEMENT:
            return
        next_dealer = room.session.next_hand_dealer_seat()
        if not room.is_bot_seat(next_dealer):
            return
        room.session.start_new_hand()
        await _broadcast_state(room)

    asyncio.create_task(_advance())


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
    next_dealer = s.next_hand_dealer_seat()
    auto_advance = 10.0 if room.is_bot_seat(next_dealer) else None
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
        "discarder_seat": hr.discarder_seat,
        "payments": hr.payments,
        "cumulative": s.cumulative_scores,
        "next_dealer_seat": next_dealer,
        "auto_advance_seconds": auto_advance,
    }, room=room.code)
    # Broadcast updated state so the scoreboard reflects the new cumulative
    # scores while the settlement modal is shown.
    await _broadcast_state(room)
    if auto_advance is not None:
        await _schedule_next_hand_auto_advance(room, auto_advance)


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

    # Only schedule normal turns once we're actually in PLAYING. Earlier phases
    # (DEALING, FLOWER_RESOLUTION) still leave subterfuge's game.phase at DRAW
    # with an all-false action mask — the model's fallback would then pick
    # DISCARD tile 0, illegally discarding a tile from the dealer's hand.
    if hand.phase != HandPhase.PLAYING:
        return

    # Bot's normal turn (draw + discard). No pre-delay — the 2s claim window
    # that gates each discard already gives humans time to interrupt.
    # A tiny 0.3s pace makes successive bot turns feel less jarring without
    # adding meaningful wait.
    token = (hand, active, len(hand.event_log))

    async def _do_bot_turn():
        try:
            await asyncio.sleep(0.3)
            if room.session is None or room.session.current_hand is not hand:
                return
            if hand.phase != HandPhase.PLAYING or hand.claim_window is not None:
                return
            if (hand, _active_seat(hand), len(hand.event_log)) != token:
                return
            await _execute_bot_action(room, active)
        except Exception as e:
            print(f"[bot] seat={active} turn task crashed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            # Last-ditch: try a safe discard so we don't hang the room.
            try:
                await _bot_safe_fallback_discard(room, active)
            except Exception:
                pass

    asyncio.create_task(_do_bot_turn())


async def _execute_bot_action(room: Room, seat: int) -> None:
    """Run one bot action turn: query model, apply action, broadcast."""
    s = room.session
    if not s:
        return
    hand = s.current_hand
    if hand is None:
        return
    # Defense in depth: don't act if we're not in PLAYING phase. The mask is
    # all-false during DRAW/DEALING/FLOWER_RESOLUTION, and the model's fallback
    # would otherwise pick DISCARD tile 0 and corrupt the dealer's hand.
    if hand.phase != HandPhase.PLAYING or hand.claim_window is not None:
        return

    from subterfuge.env.action_space import index_to_action
    from subterfuge.types import ActionType, TurnPhase
    from server.bot import choose_action_index

    # Subterfuge's action space has no DRAW action — the engine expects the
    # caller to pull from the wall before asking the model what to do. If
    # we're sitting in DRAW phase, draw now and broadcast; the next bot turn
    # will be scheduled by _broadcast_state to handle the resulting DISCARD.
    if hand.game.phase == TurnPhase.DRAW:
        try:
            if hand.must_draw_back:
                hand.draw_back()
            else:
                hand.draw_front()
        except Exception as e:
            print(f"[bot] seat={seat} error drawing: {e}", file=sys.stderr)
            return
        if hand.phase.value == "SETTLEMENT":
            await _settle_single_or_multi(room)
            return
        await _broadcast_state(room)
        return

    try:
        idx = choose_action_index(hand.game, seat)
        action = index_to_action(idx, seat, hand.game)
        atype = action.action_type
    except Exception as e:
        print(f"[bot] seat={seat} error choosing action: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        await _bot_safe_fallback_discard(room, seat)
        return

    # Pre-validate so we never call into a hand-mutation path with an action
    # the model picked off-mask. If validation fails, fall back to a discard
    # so the game progresses instead of hanging on a silent exception.
    player = hand.game.players[seat]
    if atype == ActionType.GANG_ADD and action.tile not in player.can_gang_add():
        print(
            f"[bot] seat={seat} GANG_ADD on {action.tile} has no matching peng; falling back",
            file=sys.stderr,
        )
        await _bot_safe_fallback_discard(room, seat)
        return
    if atype == ActionType.GANG_SELF and action.tile not in player.can_gang_self():
        print(
            f"[bot] seat={seat} GANG_SELF on {action.tile} not 4-of-a-kind; falling back",
            file=sys.stderr,
        )
        await _bot_safe_fallback_discard(room, seat)
        return
    if atype == ActionType.HU:
        from subterfuge.engine.hand_eval import is_winning_hand
        if not is_winning_hand(player.hand, len(player.melds)):
            print(
                f"[bot] seat={seat} HU but hand not winning; falling back",
                file=sys.stderr,
            )
            await _bot_safe_fallback_discard(room, seat)
            return

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
            hand.declare_self_hu()
            if hand.phase.value == "SETTLEMENT":
                await _settle_single_or_multi(room)
                return
        else:
            # Model returned PASS or something unexpected for a DISCARD-phase
            # turn — keep the game moving with a fallback discard.
            print(f"[bot] seat={seat} unhandled action type {atype}; falling back", file=sys.stderr)
            await _bot_safe_fallback_discard(room, seat)
            return
    except Exception as e:
        print(f"[bot] seat={seat} error executing action {atype}: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        p = hand.game.players[seat]
        in_hand = [t for t in range(34) if int(p.hand[t]) > 0]
        print(
            f"[bot] seat={seat} hand_tiles={in_hand} melds={len(p.melds)} "
            f"pending_flowers={hand.pending_flowers[seat]}",
            file=sys.stderr,
        )
        await _bot_safe_fallback_discard(room, seat)
        return

    await _broadcast_state(room)


async def _bot_safe_fallback_discard(room: Room, seat: int) -> None:
    """Last-resort: discard the first in-hand tile and broadcast.

    Used when the bot's chosen action fails validation or mutation. Without
    this safety net the game would silently hang waiting for a bot whose
    turn was eaten by a swallowed exception.
    """
    s = room.session
    if not s:
        return
    hand = s.current_hand
    if hand is None or hand.phase != HandPhase.PLAYING:
        return
    if hand.claim_window is not None:
        # We never reach here mid-claim — but if state somehow drifted, bail.
        return
    if hand.game.phase != TurnPhase.DISCARD or hand.game.current_player != seat:
        return
    player = hand.game.players[seat]
    target = next((t for t in range(34) if int(player.hand[t]) > 0), None)
    if target is None:
        print(f"[bot] seat={seat} fallback: no tile to discard", file=sys.stderr)
        return
    try:
        hand.apply_discard(target)
        hand.open_claim_window(discarder=seat, tile=target, is_robbing_kong=False)
        await _broadcast_state(room)
        await _start_claim_window_drivers(room)
    except Exception as e:
        print(f"[bot] seat={seat} fallback discard failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
