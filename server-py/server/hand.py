"""Per-hand orchestrator: wraps subterfuge.engine.Game + our extra state."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional

from subterfuge.engine.game import Game, GameConfig
from subterfuge.engine.rulesets.dan_full import DAN_FULL_RULESET
from subterfuge.tiles import is_flower
from subterfuge.types import Wind, TurnPhase

from server.dice import roll_dice, rotate_wall_for_break, compute_break_position
from server.protocol import DiceResult, HandPhase, AvailableAction

INITIAL_HAND_SIZE = 16
DEAL_BATCH = 4


@dataclass
class ClaimWindow:
    started_at: float
    discarder: int
    tile: int
    is_robbing_kong: bool
    pending_seats: set[int] = field(default_factory=set)
    decisions: dict[int, dict | None] = field(default_factory=dict)
    waiters: set[int] = field(default_factory=set)


class Hand:
    """Drives one hand of TW 16-tile mahjong on top of subterfuge.Game.

    We never call Game.setup() or Game.do_draw() — both auto-resolve flowers,
    which we want client-driven. We use Game for: phase machine, claim
    resolution, scoring, and step() for non-draw actions.
    """

    def __init__(
        self,
        dealer_seat: int,
        round_wind_index: int,
        dealer_streak: int,
        seed: Optional[int] = None,
    ) -> None:
        self.dealer_seat = dealer_seat
        self.round_wind_index = round_wind_index
        self.dealer_streak = dealer_streak
        self._rng = random.Random(seed)

        config = GameConfig(
            num_players=4,
            initial_hand_size=INITIAL_HAND_SIZE,
            dealer=dealer_seat,
            round_wind=Wind(round_wind_index),
            consecutive_dealer_wins=dealer_streak,
            scoring_ruleset=DAN_FULL_RULESET,
            seed=seed,
        )
        self.game = Game(config)
        # Game.__init__ calls Wall().__init__(seed) which already shuffled —
        # we do NOT call game.setup() (it would auto-flower).

        self.phase: HandPhase = HandPhase.PRE_DICE
        self.dice_result: Optional[DiceResult] = None
        self.must_draw_back: bool = False
        self.pending_flowers: list[list[int]] = [[], [], [], []]
        self.wall_rotation_offset: int = 0
        self.claim_window: Optional[ClaimWindow] = None
        # Seats that won this hand (filled in when hu fires; used by serialize
        # to expose each winner's full hand at settlement time).
        self.winner_seats: list[int] = []

        # Player-visible event log: list of {seat, kind, tile?, extra?} dicts.
        # Kinds: draw_front, draw_back, discard, declare_flower, peng, chi,
        # gang_open, gang_concealed, gang_added, hu, robbing_kong_hu.
        self.event_log: list[dict] = []

    def _log_event(self, seat: int, kind: str, **extra) -> None:
        entry = {"seat": seat, "kind": kind}
        entry.update(extra)
        self.event_log.append(entry)

    def roll_dice(self) -> DiceResult:
        if self.phase != HandPhase.PRE_DICE:
            raise RuntimeError(f"roll_dice not allowed in phase {self.phase}")
        result = roll_dice(self._rng, dealer_seat=self.dealer_seat)
        self.dice_result = result

        # Rotate wall so the break point is at index 0
        seat, stack = compute_break_position(self.dealer_seat, result.sum)
        from server.wall_view import TILES_PER_SEAT
        self.wall_rotation_offset = seat * TILES_PER_SEAT + stack * 2
        self.game.wall.tiles = rotate_wall_for_break(
            self.game.wall.tiles, seat, stack,
        )
        # Reset Wall pointers (they were set by __init__ before our rotation).
        self.game.wall._front = 0
        self.game.wall._back = len(self.game.wall.tiles) - 1

        self.phase = HandPhase.DEALING
        return result

    def deal_initial_hands(self) -> None:
        """Deal 16 to each, plus 1 extra for dealer = 17.

        Uses Wall.draw() directly. Flowers go straight into pending_flowers at
        this stage (they are NOT auto-replaced yet); the server resolves them
        automatically in round-robin order after dealing is complete.
        """
        if self.phase != HandPhase.DEALING:
            raise RuntimeError(f"deal not allowed in phase {self.phase}")

        order = [(self.dealer_seat + i) % 4 for i in range(4)]
        for _ in range(INITIAL_HAND_SIZE // DEAL_BATCH):  # 4 rounds of 4
            for seat in order:
                for _ in range(DEAL_BATCH):
                    tile = self.game.wall.draw()
                    assert tile is not None
                    self._place_initial_tile(seat, tile)
        # Dealer's 17th tile.
        tile = self.game.wall.draw()
        assert tile is not None
        self._place_initial_tile(self.dealer_seat, tile)

        self.phase = HandPhase.FLOWER_RESOLUTION

    def _place_initial_tile(self, seat: int, tile: int) -> None:
        """Place a freshly-drawn initial tile into a seat's hand or pending flowers.

        Per spec, flowers do NOT auto-replace at deal time — they sit in the
        player's pending-flowers list (visible as "in hand" on the client UI)
        until the player explicitly declares each one in FLOWER_RESOLUTION.
        Subterfuge's Player.hand only stores non-flower tile IDs (0..33).
        """
        if is_flower(tile):
            self.pending_flowers[seat].append(tile)
        else:
            self.game.players[seat].add_tile(tile)

    # ---- Flower resolution (auto-server-side) ----------------------------------

    def auto_resolve_round_for_seat(self, seat: int) -> list[dict]:
        """Resolve all currently-pending flowers for `seat` in ONE round.

        Snapshots seat's current pending_flowers, then for each: moves to
        player.flowers and draws a replacement from the back of the wall.
        Replacements that are themselves flowers go into pending_flowers[seat]
        for the NEXT round; non-flower replacements go into the player's hand.

        Returns a list of step dicts for client animation:
            [{"flower": id, "replacement": id_or_None, "replacement_is_flower": bool}, ...]
        If a replacement draw exhausts the wall, the function stops, sets
        SETTLEMENT phase, and the last step has "wall_exhausted": True.
        """
        steps: list[dict] = []
        if not self.pending_flowers[seat]:
            return steps
        # Snapshot the queue for this round so newly-arrived flowers wait.
        this_round = list(self.pending_flowers[seat])
        self.pending_flowers[seat] = []
        next_round: list[int] = []
        for flower in this_round:
            self.game.players[seat].add_flower(flower)
            self._log_event(seat, "declare_flower", tile=flower)
            replacement = self.game.wall.draw_replacement()
            if replacement is None:
                self.phase = HandPhase.SETTLEMENT
                self.game.phase = TurnPhase.GAME_OVER
                steps.append({"flower": flower, "replacement": None,
                              "replacement_is_flower": False, "wall_exhausted": True})
                # Keep the rest of this_round un-resolved; restore them to pending.
                # Per spec the hand ends as draw, so it doesn't really matter, but
                # leaving state consistent is safer.
                idx = this_round.index(flower)
                remaining = this_round[idx + 1:]
                self.pending_flowers[seat] = next_round + remaining
                return steps
            if is_flower(replacement):
                next_round.append(replacement)
                steps.append({"flower": flower, "replacement": replacement,
                              "replacement_is_flower": True, "wall_exhausted": False})
            else:
                self.game.players[seat].add_tile(replacement)
                steps.append({"flower": flower, "replacement": replacement,
                              "replacement_is_flower": False, "wall_exhausted": False})
        # Newly-drawn flowers wait for the next round.
        self.pending_flowers[seat] = next_round
        return steps

    def has_any_pending_flowers(self) -> bool:
        return any(self.pending_flowers[s] for s in range(4))

    def check_special_flower_win(self) -> tuple[int, int | None] | None:
        """After an auto-declaration, check for 八仙过海 / 七抢一."""
        from server.special_flowers import detect_special_flower_win
        per_seat_flowers = [
            list(self.game.players[s].flowers) + list(self.pending_flowers[s])
            for s in range(4)
        ]
        return detect_special_flower_win(
            per_seat_flowers=per_seat_flowers,
            ruleset_triggers_seven_steal=True,
        )

    def enter_playing(self) -> None:
        """Transition from FLOWER_RESOLUTION to PLAYING."""
        self.phase = HandPhase.PLAYING
        self.game.phase = TurnPhase.DISCARD
        self.game.current_player = self.dealer_seat
        self.game._is_first_draw = True
        self.game._replacement_draw = False

    def draw_back(self) -> None:
        """Draw a replacement tile from the back of the wall (for a gang).

        If the replacement is itself a flower, auto-resolve and continue
        drawing replacements until a non-flower lands.
        """
        if not self.must_draw_back:
            raise RuntimeError("no replacement draw owed")
        seat = self.game.current_player
        tile = self.game.wall.draw_replacement()
        if tile is None:
            self.phase = HandPhase.SETTLEMENT
            self.game.phase = TurnPhase.GAME_OVER
            self.must_draw_back = False
            return
        # Chain flower resolution: if we drew a flower, declare it and draw again.
        while is_flower(tile):
            self.game.players[seat].add_flower(tile)
            self._log_event(seat, "declare_flower", tile=tile)
            tile = self.game.wall.draw_replacement()
            if tile is None:
                self.phase = HandPhase.SETTLEMENT
                self.game.phase = TurnPhase.GAME_OVER
                self.must_draw_back = False
                return
        self.game.players[seat].add_tile(tile)
        self._log_event(seat, "draw_back", tile=tile)
        self.game._replacement_draw = True
        self.must_draw_back = False
        # The player who triggered the back-of-wall draw (gang) must now discard.
        self.game.phase = TurnPhase.DISCARD

    # ---- PLAYING phase: draws and discards -----------------------------------

    def draw_front(self) -> int | None:
        if self.phase != HandPhase.PLAYING:
            raise RuntimeError(f"draw_front not allowed in phase {self.phase}")
        if self.game.phase != TurnPhase.DRAW:
            raise RuntimeError(f"draw_front not allowed in game phase {self.game.phase}")
        if self.must_draw_back:
            raise RuntimeError("must draw_back, not draw_front")
        seat = self.game.current_player
        tile = self.game.wall.draw()
        if tile is None:
            # Wall exhausted on the front → hand ends as draw.
            self.phase = HandPhase.SETTLEMENT
            self.game.phase = TurnPhase.GAME_OVER
            return None
        # Chain any flower draws: each flower → declare, replacement from back.
        drew_any_flower = False
        while is_flower(tile):
            drew_any_flower = True
            self.game.players[seat].add_flower(tile)
            self._log_event(seat, "declare_flower", tile=tile)
            tile = self.game.wall.draw_replacement()
            if tile is None:
                self.phase = HandPhase.SETTLEMENT
                self.game.phase = TurnPhase.GAME_OVER
                return None
        self.game.players[seat].add_tile(tile)
        self.game.phase = TurnPhase.DISCARD
        # 杠上 flag only if the final non-flower came from the back of the wall
        # (i.e., we chained through at least one flower).
        self.game._replacement_draw = drew_any_flower
        self._log_event(seat, "draw_front", tile=tile)
        return tile

    def apply_discard(self, tile_id: int) -> None:
        from subterfuge.types import Action, ActionType
        seat = self.game.current_player
        action = Action(ActionType.DISCARD, tile=tile_id, player=seat)
        self.game.step(action)
        self._log_event(seat, "discard", tile=tile_id)

    def apply_claim(
        self,
        seat: int,
        claim_type: str,
        tiles: list[int] | None = None,
    ) -> None:
        """Apply a claim from `seat` against the current pending discard.

        Valid claim_types: 'chi', 'peng', 'gang_open', 'hu'.
        For chi, `tiles` is the [tile_a, tile_b] from claimer's hand.
        """
        if self.game.phase != TurnPhase.CLAIM_WINDOW:
            raise RuntimeError(f"no claim window (phase {self.game.phase})")
        if seat == self.game.last_discard_player:
            raise ValueError("discarder cannot claim own discard")

        from subterfuge.types import Action, ActionType, Meld, MeldType
        tile = self.game.last_discard
        discarder = self.game.last_discard_player

        if claim_type == "hu":
            action = Action(ActionType.HU, tile=tile, player=seat)
            if self.game._pending_gang_add is not None:
                # Robbing-the-kong: route through resolve_claim_window so
                # subterfuge sets _is_robbing_kong=True and clears
                # _pending_gang_add, awarding 抢杠 in DAN scoring.
                claims = {
                    i: Action(ActionType.PASS, player=i)
                    for i in range(4)
                    if i != self.game.last_discard_player
                }
                claims[seat] = action
                self.game.resolve_claim_window(claims)
            else:
                self.game.step(action)
            # Remove the claimed tile from the discarder's pile (it's now part
            # of the winner's hand for scoring purposes, not on the table).
            if discarder is not None and self.game.players[discarder].discards:
                self.game.players[discarder].discards.pop()
            kind = "robbing_kong_hu" if self.game._is_robbing_kong else "hu"
            self._log_event(seat, kind, tile=tile)
            self.winner_seats = [seat]
            self.phase = HandPhase.SETTLEMENT
            return

        if claim_type == "peng":
            meld = Meld(
                meld_type=MeldType.PENG,
                tiles=[tile, tile, tile],
                source_player=discarder,
                source_tile=tile,
            )
            action = Action(ActionType.PENG, tile=tile, player=seat, meld=meld)
            self.game.step(action)
            if discarder is not None and self.game.players[discarder].discards:
                self.game.players[discarder].discards.pop()
            self._log_event(seat, "peng", tile=tile)
            return

        if claim_type == "gang_open":
            meld = Meld(
                meld_type=MeldType.GANG_OPEN,
                tiles=[tile] * 4,
                source_player=discarder,
                source_tile=tile,
            )
            action = Action(ActionType.GANG_CALL, tile=tile, player=seat, meld=meld)
            self.game.step(action)
            if discarder is not None and self.game.players[discarder].discards:
                self.game.players[discarder].discards.pop()
            self._log_event(seat, "gang_open", tile=tile)
            self.must_draw_back = True
            return

        if claim_type == "chi":
            assert tiles is not None and len(tiles) == 2
            all_tiles = sorted(tiles + [tile])
            meld = Meld(
                meld_type=MeldType.CHI,
                tiles=all_tiles,
                source_player=discarder,
                source_tile=tile,
            )
            action = Action(
                ActionType.CHI, tile=tile, player=seat,
                meld=meld, chi_tiles=tiles,
            )
            self.game.step(action)
            if discarder is not None and self.game.players[discarder].discards:
                self.game.players[discarder].discards.pop()
            self._log_event(seat, "chi", tile=tile, with_tiles=tiles)
            return

        raise ValueError(f"unknown claim_type: {claim_type}")

    def apply_multi_hu(self, winner_seats: list[int]) -> list:
        """Score N simultaneous hu winners off the same discard.

        Iterates: hu seat A → capture result → restore → hu seat B → capture →
        ... → final restore + return a list of GameResults.
        Caller is responsible for aggregating payments.
        """
        import copy
        from subterfuge.types import Action, ActionType
        if not winner_seats:
            raise ValueError("no winners")
        if self.game.phase.name != "CLAIM_WINDOW":
            raise RuntimeError(f"multi-hu requires open claim window (phase {self.game.phase})")
        results = []
        # Snapshot the game state so we can restore for each winner.
        baseline_game = copy.deepcopy(self.game)
        for seat in winner_seats:
            action = Action(ActionType.HU, tile=self.game.last_discard, player=seat)
            self.game.step(action)
            results.append(self.game.result)
            # Restore baseline for the next winner.
            self.game = copy.deepcopy(baseline_game)
        # After the loop we're back at baseline; advance to SETTLEMENT.
        self.winner_seats = list(winner_seats)
        self.phase = HandPhase.SETTLEMENT
        return results

    def can_hu_on_tile(self, seat: int, tile_id: int) -> bool:
        """Check if `seat` could win by adding `tile_id` to their hand."""
        from subterfuge.engine.hand_eval import is_winning_hand
        p = self.game.players[seat]
        test_hand = p.hand.copy()
        test_hand[tile_id] += 1
        return is_winning_hand(test_hand, len(p.melds))

    # ---- Claim window management -------------------------------------------

    def open_claim_window(self, discarder: int, tile: int, is_robbing_kong: bool = False) -> None:
        non_discarders = [s for s in range(4) if s != discarder]
        self.claim_window = ClaimWindow(
            started_at=time.monotonic(),
            discarder=discarder,
            tile=tile,
            is_robbing_kong=is_robbing_kong,
            pending_seats=set(non_discarders),
            decisions={},
            waiters=set(),
        )

    def record_claim_decision(self, seat: int, decision: dict) -> None:
        """decision is {"action": "pass"|"peng"|"chi"|"gang_open"|"hu", "tiles"?: [...]}."""
        cw = self.claim_window
        if cw is None or seat not in cw.pending_seats:
            return
        cw.decisions[seat] = decision
        cw.pending_seats.discard(seat)
        cw.waiters.discard(seat)

    def record_wait_toggle(self, seat: int, wait: bool) -> None:
        cw = self.claim_window
        if cw is None or seat not in cw.pending_seats:
            return
        if wait:
            cw.waiters.add(seat)
        else:
            cw.waiters.discard(seat)

    def claim_window_resolvable(self) -> bool:
        cw = self.claim_window
        if cw is None:
            return False
        return (
            len(cw.pending_seats) == 0
            and len(cw.waiters) == 0
            and (time.monotonic() - cw.started_at) >= 2.0
        )

    def claim_window_remaining_seconds(self) -> float:
        cw = self.claim_window
        if cw is None:
            return 0.0
        return max(0.0, 2.0 - (time.monotonic() - cw.started_at))

    def close_claim_window(self) -> None:
        self.claim_window = None

    def declare_concealed_gang(self, tile_id: int) -> None:
        from subterfuge.types import Action, ActionType, Meld, MeldType
        seat = self.game.current_player
        meld = Meld(meld_type=MeldType.GANG_CONCEALED, tiles=[tile_id] * 4)
        action = Action(ActionType.GANG_SELF, tile=tile_id, player=seat, meld=meld)
        self.game.step(action)
        self._log_event(seat, "gang_concealed", tile=tile_id)
        self.must_draw_back = True

    def declare_added_gang(self, tile_id: int) -> None:
        from subterfuge.types import Action, ActionType, Meld, MeldType
        seat = self.game.current_player
        # Find the source_player of the existing peng (for meld provenance).
        src = next(
            m.source_player for m in self.game.players[seat].melds
            if m.meld_type == MeldType.PENG and m.tiles[0] == tile_id
        )
        meld = Meld(
            meld_type=MeldType.GANG_ADD,
            tiles=[tile_id] * 4,
            source_player=src,
            source_tile=tile_id,
        )
        action = Action(ActionType.GANG_ADD, tile=tile_id, player=seat, meld=meld)
        self.game.step(action)
        self._log_event(seat, "gang_added", tile=tile_id)
        # NOTE: subterfuge's _handle_gang_add stages last_discard for the robbing
        # window. must_draw_back is set later by close_claim_window_no_winner via
        # _complete_gang_add inside subterfuge.

    def declare_self_hu(self) -> None:
        from subterfuge.types import Action, ActionType
        seat = self.game.current_player
        hu_tile = self.game.players[seat]._just_drew or -1
        action = Action(
            ActionType.HU,
            tile=hu_tile,
            player=seat,
        )
        self.game.step(action)
        self._log_event(seat, "hu", tile=hu_tile, self_draw=True)
        self.winner_seats = [seat]
        self.phase = HandPhase.SETTLEMENT

    def close_claim_window_no_winner(self) -> None:
        """Close the claim window with no winning claim; advance to next player's draw.

        Used when the next player explicitly draws (closing the window). For
        Phase 2.3 this is just a helper; full claim-window logic lands in 3.x.
        """
        if self.game.phase != TurnPhase.CLAIM_WINDOW:
            raise RuntimeError(f"no claim window open (phase {self.game.phase})")
        from subterfuge.types import Action, ActionType
        was_pending_add = self.game._pending_gang_add is not None
        # Build an all-pass claim dict to delegate resolution to subterfuge.
        claims = {
            i: Action(ActionType.PASS, player=i)
            for i in range(4)
            if i != self.game.last_discard_player
        }
        self.game.resolve_claim_window(claims)
        if was_pending_add and self.game.phase == TurnPhase.DRAW:
            self.must_draw_back = True

    def available_actions(self, seat: int) -> list[AvailableAction]:
        if self.phase == HandPhase.PRE_DICE:
            return [AvailableAction.ROLL_DICE] if seat == self.dealer_seat else []

        if self.phase == HandPhase.DEALING:
            return []

        if self.phase == HandPhase.FLOWER_RESOLUTION:
            return []  # auto-resolved by the server; no user action needed

        if self.phase == HandPhase.SETTLEMENT:
            # next-hand control handled at session level; return [] here.
            return []

        # PLAYING
        result: list[AvailableAction] = []
        is_current = (seat == self.game.current_player)

        if self.game.phase == TurnPhase.DRAW and is_current:
            result.append(AvailableAction.DRAW_BACK if self.must_draw_back
                          else AvailableAction.DRAW_FRONT)

        if self.game.phase == TurnPhase.DISCARD and is_current:
            if self.must_draw_back:
                result.append(AvailableAction.DRAW_BACK)
            else:
                result.append(AvailableAction.DISCARD)
                p = self.game.players[seat]
                if p.can_gang_self():
                    result.append(AvailableAction.DECLARE_CONCEALED_GANG)
                if p.can_gang_add():
                    result.append(AvailableAction.DECLARE_ADDED_GANG)
                from subterfuge.engine.hand_eval import is_winning_hand
                if is_winning_hand(p.hand, len(p.melds)):
                    result.append(AvailableAction.HU)

        if self.game.phase == TurnPhase.CLAIM_WINDOW and seat != self.game.last_discard_player:
            from subterfuge.types import ActionType
            # Normal post-discard claim window.
            valid = self.game.get_valid_actions(seat)
            for a in valid:
                if a.action_type == ActionType.HU:
                    result.append(AvailableAction.HU)
                elif a.action_type == ActionType.PENG:
                    result.append(AvailableAction.PENG)
                elif a.action_type == ActionType.GANG_CALL:
                    result.append(AvailableAction.GANG_OPEN)
                elif a.action_type == ActionType.CHI:
                    result.append(AvailableAction.CHI)

        # Deduplicate while preserving order.
        seen: set[AvailableAction] = set()
        deduped = []
        for a in result:
            if a not in seen:
                seen.add(a)
                deduped.append(a)
        return deduped
