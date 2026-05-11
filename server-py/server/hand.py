"""Per-hand orchestrator: wraps subterfuge.engine.Game + our extra state."""
from __future__ import annotations

import random
from typing import Optional

from subterfuge.engine.game import Game, GameConfig
from subterfuge.engine.rulesets.dan_full import DAN_FULL_RULESET
from subterfuge.tiles import is_flower
from subterfuge.types import Wind, TurnPhase

from server.dice import roll_dice, rotate_wall_for_break, compute_break_position
from server.protocol import DiceResult, HandPhase

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

    def roll_dice(self) -> DiceResult:
        if self.phase != HandPhase.PRE_DICE:
            raise RuntimeError(f"roll_dice not allowed in phase {self.phase}")
        result = roll_dice(self._rng, dealer_seat=self.dealer_seat)
        self.dice_result = result

        # Rotate wall so the break point is at index 0
        seat, stack = compute_break_position(self.dealer_seat, result.sum)
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

    def close_claim_window_no_winner(self) -> None:
        """Close the claim window with no winning claim; advance to next player's draw.

        Used when the next player explicitly draws (closing the window). For
        Phase 2.3 this is just a helper; full claim-window logic lands in 3.x.
        """
        if self.game.phase != TurnPhase.CLAIM_WINDOW:
            raise RuntimeError(f"no claim window open (phase {self.game.phase})")
        from subterfuge.types import Action, ActionType
        # Build an all-pass claim dict to delegate resolution to subterfuge.
        claims = {
            i: Action(ActionType.PASS, player=i)
            for i in range(4)
            if i != self.game.last_discard_player
        }
        self.game.resolve_claim_window(claims)
