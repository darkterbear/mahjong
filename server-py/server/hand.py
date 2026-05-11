"""Per-hand orchestrator: wraps subterfuge.engine.Game + our extra state."""
from __future__ import annotations

import random
from typing import Optional

from subterfuge.engine.game import Game, GameConfig
from subterfuge.engine.rulesets.dan_full import DAN_FULL_RULESET
from subterfuge.tiles import is_flower
from subterfuge.types import Wind, TurnPhase

from server.dice import roll_dice, rotate_wall_for_break, compute_break_position
from server.protocol import DiceResult, HandPhase, AvailableAction

INITIAL_HAND_SIZE = 16
DEAL_BATCH = 4


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
        self.flower_resolution_seat: int = 0
        self.must_draw_back: bool = False
        self._snapshots: list = []
        self.pending_flowers: list[list[int]] = [[], [], [], []]
        self.wall_rotation_offset: int = 0
        self.co_hu_joined: list[int] = []
        self.co_hu_remaining: list[int] = []
        self.co_hu_declined: list[int] = []
        self.co_hu_active: bool = False

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

        Uses Wall.draw() directly. Flowers go straight into hand at this
        stage (they are NOT auto-replaced); the client resolves them in the
        FLOWER_RESOLUTION phase.
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
        self._begin_flower_resolution()

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

    # ---- Flower resolution ----------------------------------------------------

    def _begin_flower_resolution(self) -> None:
        self.flower_resolution_seat = self.dealer_seat
        self.must_draw_back = False
        self._advance_flower_resolution_seat_if_clean()

    def declare_flower(self, tile_id: int) -> None:
        if self.phase not in (HandPhase.FLOWER_RESOLUTION, HandPhase.PLAYING):
            raise RuntimeError(f"declare_flower not allowed in phase {self.phase}")
        if not is_flower(tile_id):
            raise ValueError(f"tile {tile_id} is not a flower")
        seat = self._active_flower_seat()
        if tile_id not in self.pending_flowers[seat]:
            raise ValueError(f"seat {seat} does not hold flower {tile_id}")
        self.pending_flowers[seat].remove(tile_id)
        self.game.players[seat].add_flower(tile_id)
        self.must_draw_back = True

    def _active_flower_seat(self) -> int:
        if self.phase == HandPhase.FLOWER_RESOLUTION:
            return self.flower_resolution_seat
        return self.game.current_player

    def draw_back(self) -> None:
        if not self.must_draw_back:
            raise RuntimeError("no replacement draw owed")
        tile = self.game.wall.draw_replacement()
        if tile is None:
            # Wall exhausted on a replacement — hand ends as draw.
            self.phase = HandPhase.SETTLEMENT
            self.game.phase = TurnPhase.GAME_OVER
            self.must_draw_back = False
            return
        seat = self._active_flower_seat()
        if is_flower(tile):
            # Replacement was itself a flower — pending list, will need another draw_back.
            self.pending_flowers[seat].append(tile)
            # must_draw_back stays True implicitly only if the player declares
            # this newly-arrived flower next. Spec: each draw_back resolves one
            # owed replacement; subsequent flower handling is its own declare→draw_back cycle.
            self.must_draw_back = False
        else:
            self.game.players[seat].add_tile(tile)
            # Flag for 杠上 if we're in PLAYING (replacement after gang/flower).
            if self.phase == HandPhase.PLAYING:
                self.game._replacement_draw = True
            self.must_draw_back = False
        if self.phase == HandPhase.FLOWER_RESOLUTION:
            self._advance_flower_resolution_seat_if_clean()
            self._maybe_finish_flower_resolution()

    def _advance_flower_resolution_seat_if_clean(self) -> None:
        """If the active flower-resolution seat has no pending flowers, advance to next seat."""
        while True:
            if self._has_flower_in_hand(self.flower_resolution_seat):
                return
            next_seat = (self.flower_resolution_seat + 1) % 4
            if next_seat == self.dealer_seat:
                # Cycled all 4 — done.
                return
            self.flower_resolution_seat = next_seat

    def _has_flower_in_hand(self, seat: int) -> bool:
        return len(self.pending_flowers[seat]) > 0

    def _maybe_finish_flower_resolution(self) -> None:
        if self.phase != HandPhase.FLOWER_RESOLUTION:
            return
        if any(self._has_flower_in_hand(s) for s in range(4)):
            return
        # All clean → enter PLAYING.
        self.phase = HandPhase.PLAYING
        self.game.phase = TurnPhase.DISCARD  # dealer already drew their 17th
        self.game.current_player = self.dealer_seat
        self.game._is_first_draw = True
        self.game._replacement_draw = False

    # ---- PLAYING phase: draws and discards -----------------------------------

    def draw_front(self) -> int | None:
        if self.phase != HandPhase.PLAYING:
            raise RuntimeError(f"draw_front not allowed in phase {self.phase}")
        if self.game.phase != TurnPhase.DRAW:
            raise RuntimeError(f"draw_front not allowed in game phase {self.game.phase}")
        if self.must_draw_back:
            raise RuntimeError("must draw_back, not draw_front")
        tile = self.game.wall.draw()
        if tile is None:
            # Wall exhausted → hand ends as draw.
            self.phase = HandPhase.SETTLEMENT
            self.game.phase = TurnPhase.GAME_OVER
            return None
        seat = self.game.current_player
        if is_flower(tile):
            self.pending_flowers[seat].append(tile)
        else:
            self.game.players[seat].add_tile(tile)
        self.game.phase = TurnPhase.DISCARD
        # Reset replacement-draw flag (this was a normal front draw).
        self.game._replacement_draw = False
        return tile

    def apply_discard(self, tile_id: int) -> None:
        from subterfuge.types import Action, ActionType
        action = Action(ActionType.DISCARD, tile=tile_id, player=self.game.current_player)
        self.game.step(action)

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
            return

        raise ValueError(f"unknown claim_type: {claim_type}")

    def apply_multi_hu(self, winner_seats: list[int]) -> list:
        """Score N simultaneous hu winners off the same discard.

        Snapshots before the first hu, then iterates: hu seat A → capture
        result → restore → hu seat B → capture → ... → final restore + return
        a list of GameResults. Caller is responsible for aggregating payments.
        """
        from subterfuge.types import Action, ActionType
        if not winner_seats:
            raise ValueError("no winners")
        if self.game.phase.name != "CLAIM_WINDOW":
            raise RuntimeError(f"multi-hu requires open claim window (phase {self.game.phase})")
        results = []
        # Take a fresh snapshot for the multi-hu walk.
        self.snapshot()
        baseline_idx = len(self._snapshots) - 1
        for seat in winner_seats:
            action = Action(ActionType.HU, tile=self.game.last_discard, player=seat)
            self.game.step(action)
            results.append(self.game.result)
            # Restore baseline for the next winner.
            from server.undo import restore_snapshot
            restore_snapshot(self, self._snapshots[baseline_idx])
        # After the loop we're back at baseline; advance to SETTLEMENT.
        self.phase = HandPhase.SETTLEMENT
        return results

    def can_hu_on_tile(self, seat: int, tile_id: int) -> bool:
        """Check if `seat` could win by adding `tile_id` to their hand."""
        from subterfuge.engine.hand_eval import is_winning_hand
        p = self.game.players[seat]
        test_hand = p.hand.copy()
        test_hand[tile_id] += 1
        return is_winning_hand(test_hand, len(p.melds))

    def start_co_hu_window(self, initial_seat: int) -> None:
        """Enter the co-hu window. The first hu claim has just arrived from initial_seat.

        Computes which other non-discarder seats can ALSO hu on the pending tile
        and pauses settlement until each responds.
        """
        if self.game.phase.name != "CLAIM_WINDOW":
            raise RuntimeError(f"co-hu requires open claim window (phase {self.game.phase})")
        tile = self.game.last_discard
        discarder = self.game.last_discard_player
        others = []
        for seat in range(4):
            if seat == initial_seat or seat == discarder:
                continue
            if self.can_hu_on_tile(seat, tile):
                others.append(seat)
        self.co_hu_joined = [initial_seat]
        self.co_hu_remaining = others
        self.co_hu_declined = []
        self.co_hu_active = True

    def record_co_hu_response(self, seat: int, accept: bool) -> None:
        if not self.co_hu_active:
            raise RuntimeError("no co-hu window open")
        if seat not in self.co_hu_remaining:
            raise ValueError(f"seat {seat} is not in remaining co-hu responders")
        self.co_hu_remaining.remove(seat)
        if accept:
            self.co_hu_joined.append(seat)
        else:
            self.co_hu_declined.append(seat)

    def co_hu_complete(self) -> bool:
        return self.co_hu_active and not self.co_hu_remaining

    def finalize_co_hu(self) -> list:
        """Run apply_multi_hu with all joined winners; return the list of GameResults."""
        if not self.co_hu_complete():
            raise RuntimeError("co-hu not yet complete")
        winners = list(self.co_hu_joined)
        self.co_hu_active = False
        self.co_hu_joined = []
        self.co_hu_remaining = []
        self.co_hu_declined = []
        return self.apply_multi_hu(winners)

    def declare_concealed_gang(self, tile_id: int) -> None:
        from subterfuge.types import Action, ActionType, Meld, MeldType
        seat = self.game.current_player
        meld = Meld(meld_type=MeldType.GANG_CONCEALED, tiles=[tile_id] * 4)
        action = Action(ActionType.GANG_SELF, tile=tile_id, player=seat, meld=meld)
        self.game.step(action)
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
        # NOTE: subterfuge's _handle_gang_add stages last_discard for the robbing
        # window. must_draw_back is set later by close_claim_window_no_winner via
        # _complete_gang_add inside subterfuge.

    def declare_self_hu(self) -> None:
        from subterfuge.types import Action, ActionType
        seat = self.game.current_player
        action = Action(
            ActionType.HU,
            tile=self.game.players[seat]._just_drew or -1,
            player=seat,
        )
        self.game.step(action)
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

    def snapshot(self) -> None:
        from server.undo import take_snapshot
        self._snapshots.append(take_snapshot(self))

    def undo(self) -> None:
        from server.undo import restore_snapshot
        if not self._snapshots:
            raise RuntimeError("no snapshots to undo")
        snap = self._snapshots.pop()
        restore_snapshot(self, snap)

    def clear_snapshots(self) -> None:
        self._snapshots.clear()

    def available_actions(self, seat: int) -> list[AvailableAction]:
        # CO_HU window: only eligible seats see Hu/Pass; others see nothing.
        if self.co_hu_active:
            if seat in self.co_hu_remaining:
                return [AvailableAction.HU, AvailableAction.CO_HU_PASS]
            return []

        if self.phase == HandPhase.PRE_DICE:
            return [AvailableAction.ROLL_DICE] if seat == self.dealer_seat else []

        if self.phase == HandPhase.DEALING:
            return []

        if self.phase == HandPhase.FLOWER_RESOLUTION:
            if seat != self.flower_resolution_seat:
                return []
            if self.must_draw_back:
                return [AvailableAction.DRAW_BACK]
            if self._has_flower_in_hand(seat):
                return [AvailableAction.DECLARE_FLOWER]
            return []

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
            # Player must declare flower if they hold one.
            if self._has_flower_in_hand(seat):
                result.append(AvailableAction.DECLARE_FLOWER)
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
