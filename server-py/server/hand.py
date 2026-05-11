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

    def _place_initial_tile(self, seat: int, tile: int) -> None:
        """Place a freshly-drawn initial tile into a seat's hand.

        IMPORTANT: per spec we DO NOT replace flowers automatically. The
        flower stays in the player's hand until they click DECLARE_FLOWER.
        """
        self.game.players[seat].add_tile(tile)
