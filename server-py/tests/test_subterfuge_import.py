"""Smoke test that subterfuge imports through the path dep."""
from __future__ import annotations


def test_subterfuge_imports() -> None:
    from subterfuge.tiles import NUM_TILE_TYPES, TOTAL_TILES
    assert NUM_TILE_TYPES == 34
    assert TOTAL_TILES == 144


def test_subterfuge_engine_imports() -> None:
    from subterfuge.engine.game import Game, GameConfig
    from subterfuge.engine.wall import Wall
    from subterfuge.engine.player import Player
    from subterfuge.engine.actions import resolve_claims, CLAIM_PRIORITY
    from subterfuge.engine.rulesets.dan_full import DAN_FULL_RULESET

    g = Game(GameConfig(seed=42))
    assert g.config.num_players == 4
    assert g.wall.total == 144
    assert DAN_FULL_RULESET.name == "Dan Full"
