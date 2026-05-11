# Taiwanese 16-tile Mahjong Redesign

**Date:** 2026-05-10
**Status:** Approved (auto-approved by user 2026-05-10)

## Goal

Convert the existing HK 13-tile mahjong web app into a Taiwanese 16-tile variant with full DAN scoring (per `~/subterfuge`), an interactive click-to-draw UI that surfaces the wall, and a multi-hand session model with dealer rotation. Targeted at voice-call group play — every interaction is undoable at the current player's discretion.

## Non-goals

- Detection evasion, AI play, or RL hooks (subterfuge handles that separately and is not modified).
- Mobile responsiveness beyond what the existing layout achieves.
- Spectator mode, replays, or persistence across server restarts.
- Authentication beyond the existing session-id / username flow.

## Inputs already settled (brainstorming)

- **Rules / scoring:** Taiwanese 16-tile, 144 tiles incl. 8 flowers; DAN_FULL ruleset from subterfuge — every tai (concealed pungs/gangs, qiang gang, tian/di hu, eight immortals, etc.).
- **Session model:** open-ended hands with cumulative scores. Dealer rotation per TW rules. Header always shows current round wind + dealer streak.
- **Interaction model:** all draws click-based (no auto, including flower/gang replacements). 0.5s server-enforced gap between discard and next draw. No hard timer for chi/peng/gang/hu — claim window stays open until the next draw lands. Current player has an Undo button that chains back to hand start.
- **Action UX:** contextual action bar (buttons for Chi/Peng/Gang/Hu/Pass on claim windows; Hu/Concealed Gang/Add Gang on self-turn). Disambiguation (e.g. multiple chi options) highlights tiles in hand to click.
- **End-of-hand:** modal with full DAN breakdown + per-player payment + cumulative scores. Persistent scoreboard panel always visible. Only the next hand's dealer can advance with "Next Hand".
- **Wall display:** classical perimeter wall on all 4 sides, between hands and discards, with the next-to-draw tile highlighted (front for normal draw, back for replacement).
- **Existing flow preserved:** menu / join / lobby / 4-letter code rooms; existing Cangjie6 SVG tile assets (8 flower SVGs to be added by user).
- **Stack:** Python server (FastAPI + python-socketio) imports subterfuge as a library; React client kept, only `GamePage` rewritten.

## Architecture

### Repo layout

```
mahjong/                          (root, existing)
├── client/                       React app (kept; only GamePage redone)
├── server/                       NEW: Python server, replaces Node server
│   ├── pyproject.toml
│   ├── server/
│   │   ├── app.py                FastAPI + socketio attach + uvicorn entrypoint
│   │   ├── routes.py             /create_room, /join_room, /start_session
│   │   ├── sockets.py            socket event handlers
│   │   ├── room.py               Room registry + Player + lobby
│   │   ├── session.py            Multi-hand session: dealer rotation, scores, round wind
│   │   ├── hand.py               Per-hand orchestrator wrapping subterfuge.Game
│   │   ├── dice.py               3d6 + break-point computation + deal-script generator
│   │   ├── undo.py               Snapshot stack (deepcopy)
│   │   ├── serialize.py          Game state → per-player wire JSON
│   │   └── protocol.py           Event names, action enums, dataclasses
│   └── tests/
├── subterfuge/                   git submodule → git@github.com:darkterbear/subterfuge.git
├── shared-tiles/                 tiny TS helper: tile-id → image url, suit constants
├── ecosystem.config.js           updated: uvicorn instead of node
└── docs/superpowers/specs/       this file
```

The old `mahjong/` (TS lib) and `server/` (Node) directories are removed. The new `server/` is Python.

### Subterfuge import strategy

- Subterfuge is a git submodule at `mahjong/subterfuge/` pointing at `git@github.com:darkterbear/subterfuge.git`.
- The mahjong repo pins a SHA — bumping requires a deliberate commit.
- `server/pyproject.toml` declares `subterfuge = {path = "../subterfuge", develop = true}` (path dependency, editable in dev).
- "Don't touch subterfuge" is enforced by the submodule boundary — edits would surface as a dirty submodule needing a commit into the subterfuge repo.

**Dev:** `git clone --recurse-submodules ... && cd server && python -m venv .venv && source .venv/bin/activate && pip install -e .`

**Prod:** same, but `pip install .` (non-editable). PM2 invokes `server/.venv/bin/uvicorn server.app:app --host 0.0.0.0 --port $PORT`.

### Adapter to subterfuge.Game

Subterfuge's `Game.draw()` auto-resolves flowers internally; we don't want that. The `hand.py` orchestrator wraps `Game` so that:

- We never call `Game.draw()` directly. On `draw_front` event, we pop a tile from `Wall` ourselves and stash it as the active player's `drawn_tile`. A separate (internal) "commit draw" finalizes the tile into the player's hand via the lowest-level subterfuge call that doesn't auto-flower. If subterfuge doesn't expose a hand-modifying primitive that bypasses flower handling, the orchestrator manages the hand-count vector itself and only consults subterfuge for win-detection / claim-validation / scoring.
- Flower declarations and gang replacements are driven by client clicks. Each one increments a "must draw from back next" flag and updates `available_actions` accordingly.
- Subterfuge's `actions.get_valid_claims`, `get_self_actions`, `is_winning_hand` are used as-is.

The exact extent to which we lean on `Game` vs. drive via lower-level engine modules will be decided during implementation, after a careful read of `engine/game.py` and `engine/actions.py`. The contract: subterfuge stays untouched; if its API doesn't reach what we need, we replicate just that part in `hand.py`.

## Session & hand state machine

### Room (lobby state)
4 players max. Existing `/create_room`, `/join_room`, lobby socket flow preserved. Once the room leader calls `/start_session`, the Room transitions to a Session.

### Session (multi-hand state)
Owned per-room.

| Field | Type | Notes |
|---|---|---|
| `seats` | `[PlayerId × 4]` | Random assignment to E/S/W/N at session start. Locked for the whole session. |
| `dealer_seat` | `Seat` | Starts as East (seat 0). |
| `dealer_streak` | `int` | DAN's `庄`. +1 when dealer wins or hand draws; 0 on rotation. |
| `round_wind` | `Wind` | Starts East. Advances when each seat has been dealer once this round. |
| `dealer_rotations_this_round` | `int` | 0..3; resets when round_wind advances. |
| `cumulative_scores` | `[int × 4]` | Indexed by seat. |
| `hand_history` | `list[HandResult]` | For scoreboard "last hand" + future review. |
| `current_hand` | `Hand?` | Active hand orchestrator, or None between hands. |

### Hand (per-hand state)
Owned by Session for the duration of one hand.

Phases:

```
PRE_DICE        → dealer clicks "Roll Dice"
DEALING         → animated 4-at-a-time deal; ~3s, server-driven, deterministic from dice
FLOWER_RESOLUTION  → in dealer order, each player declares own flowers + draws back-replacements
PLAYING         → subterfuge.Game DRAW → DISCARD → CLAIM_WINDOW loop
SETTLEMENT      → scoring computed + modal shown; awaiting next-hand click
```

PLAYING sub-phases (mirrored from subterfuge):
- `AWAITING_DRAW` — current player must click front of wall (or back, if they just declared flower/gang).
- `AWAITING_DISCARD` — current player must click a tile to discard, OR declare self-action (concealed gang, added gang, self-hu).
- `CLAIM_WINDOW` — most-recent discard is up for claim. Closes when next player's `draw_front` lands (≥0.5s after discard). Undoable.

### Dealer rotation on hand end

| Outcome | Effect |
|---|---|
| Dealer self-draw or wins on discard | Dealer keeps seat, `dealer_streak += 1` |
| Wall exhaustion (draw) | Dealer keeps seat, `dealer_streak += 1` |
| Non-dealer wins | Dealer rotates one seat counterclockwise (E→S→W→N), `dealer_streak = 0`, `dealer_rotations_this_round += 1` |

When `dealer_rotations_this_round == 4`: `round_wind` advances (E→S→W→N→E…), `dealer_rotations_this_round = 0`. Sessions are open-ended; cycling round_wind back to East is fine.

## Wire protocol (socket.io)

### Client → server

| Event | Payload | Sender | Valid in phase |
|---|---|---|---|
| `roll_dice` | — | dealer | PRE_DICE |
| `draw_front` | — | current player | AWAITING_DRAW |
| `draw_back` | — | current player | AWAITING_DRAW (after gang/flower) |
| `discard` | `{tile_id}` | current player | AWAITING_DISCARD |
| `declare_flower` | `{tile_id}` | any player holding flower | FLOWER_RESOLUTION; PLAYING after drawing flower |
| `claim` | `{action: chi\|peng\|gang_open\|hu, tiles?: [tile_id...]}` | any non-discarder | CLAIM_WINDOW |
| `declare_concealed_gang` | `{tile_id}` | current player | AWAITING_DISCARD |
| `declare_added_gang` | `{tile_id}` | current player | AWAITING_DISCARD |
| `declare_self_hu` | — | current player | AWAITING_DISCARD |
| `undo` | — | current player | any phase within current hand |
| `next_hand` | — | next-hand dealer | SETTLEMENT |

All actions are validated server-side against `available_actions` before applying. Invalid attempts are silently dropped with a server log entry.

### Server → client

| Event | Payload | Recipients |
|---|---|---|
| `state_update` | per-player perspective (below) | per-socket, all 4 |
| `dice_rolled` | `{d1, d2, d3, break_seat, break_offset}` | all in room |
| `dealing_step` | `{seat, count}` | all (drives 4-at-a-time animation) |
| `hand_settlement` | `{winner_seat?, winning_tile?, source: self\|discard\|rob_kong\|draw, breakdown: {tai_name: pts}, total, payments: [int×4], cumulative: [int×4]}` | all |
| `lobby_update` | existing format | all (preserved) |

`winner_seat` and `winning_tile` are absent on a wall-exhaustion draw.

### Per-player `state_update` shape

```json
{
  "phase": "PLAYING",
  "round_wind": "EAST",
  "dealer_seat": 0,
  "dealer_streak": 1,
  "current_turn_seat": 2,
  "you": {
    "seat": 1, "seat_wind": "SOUTH",
    "hand": [3, 5, 5, 12, ...],
    "melds": [{"type": "PENG", "tiles": [...], "source_seat": 3}],
    "flowers": [34, 36],
    "drawn_tile": 18,
    "score": 7
  },
  "others": [
    {
      "seat": 2, "seat_wind": "WEST", "username": "alice",
      "hand_count": 16, "melds": [...], "flowers": [...],
      "discards": [...], "score": -3
    }, ...
  ],
  "wall": {
    "remaining_front": 84,
    "remaining_back": 12,
    "next_front_position": [seat, stack_index, layer],
    "next_back_position":  [seat, stack_index, layer]
  },
  "available_actions": ["draw_front"],
  "pending_claim_window": {
    "discarder_seat": 0, "tile": 18, "your_options": ["peng", "hu"]
  },
  "can_undo": true
}
```

`available_actions` is the source of truth for which buttons appear in the action bar — server computes it per-player based on phase, hand, current claim, and self-action eligibility. The client never recomputes eligibility.

## Action handling & undo

### Apply pipeline

For each incoming client action:
1. Validate against current `available_actions` for that player. Drop if invalid.
2. Push snapshot onto the Hand's snapshot stack: `(deepcopy(subterfuge.Game), deepcopy(extra state))`.
3. Apply via subterfuge / orchestrator.
4. Recompute phase + per-player `available_actions`.
5. Broadcast `state_update` to all 4 sockets.

### Snapshot / undo

- Snapshot stack lives on the Hand. Cleared on hand boundary.
- `undo` event pops one snapshot, restores it, broadcasts `state_update`.
- After restore, "current player" may differ — Undo's owner shifts to whoever's turn the restored state has.
- Undo cannot cross hand boundaries (snapshots cleared on SETTLEMENT or PRE_DICE entry).

### 0.5s discard delay

Server stores `last_discard_t = time.monotonic()` when a `discard` is applied. `draw_front` requests are rejected if `time.monotonic() - last_discard_t < 0.5`. No timer plumbing needed; just a timestamp check on the relevant event.

### Claim window

- Opens automatically on every `discard` and on every `declare_added_gang` (for qiang gang).
- Stays open with no hard timer. Closes implicitly when the next player's `draw_front` is accepted.
- Resolution priority when multiple players claim: `hu > peng/gang > chi`.
- If multiple players hu the same tile: multi-winner. DAN scoring runs once per winner with the same source tile + discarder. Payment semantics: each winner's score is computed independently and the discarder pays each winner the full amount (winners do not share). Other (non-winning, non-discarder) players pay nothing in the discard-win case, per DAN's settle.

### Robbing the kong (qiang gang)

- When `declare_added_gang` is applied, broadcast a virtual claim window with the kong-add tile. Other players' `available_actions` includes `hu` if their hand can win on it.
- If anyone hu's: undo the gang (the snapshot taken before `declare_added_gang` is restored), apply hu with `is_robbing_kong=True`.
- If nobody claims: gang completes when the gang-declarer's subsequent `draw_back` lands, closing the window.

## Wall + click-driven draws

### Physical layout

The wall is `144 tiles → 4 sides × 18 stacks × 2 layers`. Position indexed `(seat, stack_index, layer)`:

- `seat`: 0..3, fixed seat order
- `stack_index`: 0..17, leftmost-from-that-seat's-view = 0
- `layer`: 0 (top) or 1 (bottom)

The wall is traversed circularly. The server maintains both `next_front_position` and `next_back_position` pointers; they advance in opposite directions and meet at exhaustion.

### Break point

Computed at dice-roll time:
- `break_seat = (dealer_seat + dice_sum - 1) % 4` — counts dealer as 1 then proceeds.
- `break_offset = dice_sum` stacks in from the right edge of `break_seat`'s wall.
- `next_front_position` starts at the stack to the LEFT of the break (the next tile to deal/draw from).
- `next_back_position` starts at the stack to the RIGHT of the break (the wall's last tile).

(Exact convention to be cross-checked against canonical TW rules during impl; the data model supports either direction without code changes.)

### Click flow

- On `draw_front`: server pops via subterfuge `Wall.draw()`, advances `next_front_position`, broadcasts.
- On `draw_back`: server pops via `Wall.draw_replacement()`, advances `next_back_position`, broadcasts.
- Client highlights the tile at the active position (front for normal turn, back if `available_actions` includes `draw_back`).

### Replacement-draw triggers

Declaring a flower or completing any kong sets `must_draw_from_back = True` for that player. `available_actions` becomes `["draw_back"]` until they click. Replacement chains naturally — drawing another flower from back means another `draw_back` is queued.

### Wall exhaustion

`Wall.draw()` returning None during `draw_front` ends the hand as a draw → SETTLEMENT, no winner, dealer keeps + streak +1.

## Hand setup ceremony

1. **PRE_DICE.** Dealer sees "Roll Dice" button. Others see "Waiting for dealer."
2. **Dice roll.** Server generates 3d6, computes break point, broadcasts `dice_rolled`. Client renders ~1.5s dice tumble + arrow indicator on the break-point tile.
3. **DEALING.** Server emits `dealing_step` events at ~200ms intervals: 4 tiles to dealer, then 4 to dealer's right, repeated 4 rounds → each player has 16. Then one more for dealer's 17th. Tiles populate hands client-side as events arrive; the authoritative hand state is in the next `state_update`.
4. **FLOWER_RESOLUTION.** In dealer order (dealer first, counterclockwise), each player whose hand contains flowers must declare them. `available_actions` for that player includes `declare_flower` per flower in hand. After declaring, `available_actions` becomes `["draw_back"]`; click → replacement appears in hand. Loop until that player has no flowers, then turn passes to next player. When all 4 are flower-free, phase → PLAYING with dealer as current player, in `AWAITING_DISCARD` (already drew their 17th).

## Scoring & end-of-hand

When `hu` declared (self, off discard, or robbing kong), or wall exhausted:

1. **Build `ScoringContext`** from current state: hand counts, declared melds, winning tile, source flag, seat_wind, round_wind, flowers, is_dealer, dealer_streak, is_first_draw, is_last_tile, is_robbing_kong, is_replacement_draw, other players' flowers (for 七抢一 / 八仙过海).
2. **Call `DAN_FULL_RULESET.score(ctx) → (total, breakdown)`.**
3. **Build `PaymentContext`,** call `DAN_FULL_RULESET.settle(total, breakdown, payment_ctx) → [int×4]`.
4. Apply payments to `cumulative_scores`. Append to `hand_history`.
5. Phase → SETTLEMENT, broadcast `hand_settlement`.
6. Client shows modal: winner, winning tile, full tai breakdown (Chinese names from DAN with English subtitle), per-player payment, cumulative. Persistent scoreboard updates with new cumulative + most-recent-hand summary.
7. Next-hand dealer's `available_actions` includes `next_hand`. On click → rotate dealer per win/draw rule, advance round_wind if applicable, reset Hand state, phase → PRE_DICE.

Wall-exhaustion case: no scoring, payments all zero, modal shows "Draw — wall exhausted".

## UI layout

Single-screen perimeter-wall layout:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  ┌─────────┐                  ROUND WIND: EAST                          │
│  │SCORE-   │                  DEALER STREAK: 1                          │
│  │BOARD    │                                                             │
│  │you  +7  │                  [TOP PLAYER]   xi (W)   alice             │
│  │alice -3 │                  [discards · flowers · melds]               │
│  │bob  -2  │     ┌────────────────────────────────────────────────┐     │
│  │charlie-2│     │ ▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢   ← top player wall          │     │
│  │         │ ┌──┴──────────────────────────────────────────┴──┐   │     │
│  │last hand│ │▢                  CENTER                       ▢│   │     │
│  │alice hu │ │▢ (each player's discards stack toward center)  ▢│   │     │
│  │self drw │ │▢                                               ▢│   │     │
│  │门清+2   │ │▢                                               ▢│   │     │
│  │自摸+1   │ │▢                                               ▢│   │     │
│  │平胡+5   │ │▢                                               ▢│   │     │
│  │总: 8    │ └──┬──────────────────────────────────────────┬──┘   │     │
│  └─────────┘    │ ░▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢▢ ◄ next-draw highlight│       │     │
│                 │   (your wall — 18 stacks of 2)            │       │     │
│                 └─────────────────────────────────────────────┘       │
│                                                                         │
│   YOUR FLOWERS:  ❀❀                  MELDS: [PENG 5w 5w 5w]             │
│   YOUR HAND:    🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄🀄  ←drawn↑              │
│                                                                         │
│   ┌──────────────────────────────────────────┐    [Undo]                │
│   │ ACTION BAR:  [Pong]  [Hu]                │    seat: dong (E) ★dealer│
│   └──────────────────────────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Left rail:** scoreboard with 4 cumulative + collapsible last-hand breakdown.
- **Header:** round wind + dealer streak.
- **Each side:** that player's section of the perimeter wall (18 stacks × 2 layers, oriented for that player), then their flowers + melds + discards.
- **Center:** open. Discards visually stack toward the center from each player's side.
- **Bottom (you):** flowers + melds row, then hand (drawn tile separated by a small gap), action bar above, undo + seat indicator.
- **Settlement modal (overlay):** winner banner, full DAN breakdown table (Chinese tai name + English subtitle + points), per-player payment, "Next Hand" button (enabled only for next dealer).

### Highlight style

Next-to-draw tile: orange `drop-shadow` filter (matches existing "newly arrived" style) + subtle pulse via CSS keyframes. Only one highlight active at a time (front OR back, never both).

### Action bar

Always visible at bottom-center above the hand. Shows buttons from `available_actions` (server-computed). Disambiguating chi → buttons collapse into "tile-pick mode" with eligible hand tiles highlighted.

There is no "Pass" button — the claim window closes implicitly when the next `draw_front` lands (≥0.5s after discard). A claimer who decides not to claim simply waits; the action bar disappears from their view as soon as a `state_update` reflects window closure.

## Testing strategy

- **Subterfuge integration:** drive a `Hand` through scripted action sequences with deterministic `Wall` seed; assert end-state. Subterfuge's own tests are an oracle for engine correctness — do not duplicate them.
- **Snapshot/undo:** apply N actions, undo N times, assert state == initial. Specifically test undoing across phases (PLAYING → CLAIM_WINDOW → AWAITING_DRAW back to AWAITING_DISCARD).
- **Scoring:** for each major DAN tai, build a `ScoringContext` and assert breakdown contains expected keys with expected points. Lean on subterfuge's `tests/` for scoring confidence.
- **Server protocol:** FastAPI TestClient + python-socketio test harness; simulate 4 connected clients walking through a full hand; assert state_update broadcasts.
- **Client:** smoke test via `yarn start` + manual hand. Visual claims to verify: wall positions match server, highlight on correct next-draw tile, action bar reflects `available_actions`, settlement modal shows correct breakdown.

## Open implementation questions (defer to plan)

These don't block the design but need decisions during implementation:

- Exact extent to which `Game` is used vs. driven via lower-level subterfuge primitives, decided after reading `engine/game.py`.
- Whether to enforce a server-side "pass" event to actively close claim windows, or rely solely on the next `draw_front`. Current spec: rely on draw.
- Pixel-level layout for the perimeter wall on smaller viewports (the existing layout is desktop-first; we keep that).
- Whether the existing 4-letter room code generator stays (yes by default unless prod observability suggests collisions).

## Risks

- **Subterfuge API gaps.** `Game.draw` auto-resolves flowers; if no clean way to bypass, we re-implement the affected primitives in `hand.py`. Risk is low (subterfuge is well-factored) but mitigation is "vendor the relevant lines" with attribution comments.
- **Multi-winner hu on a single discard** is supported by DAN settlement (`sole_payer` not used; each winner takes from the discarder), but the engine integration needs careful test coverage.
- **Snapshot deepcopy cost.** 4-player game state is small; deepcopy per action is fine. Hand snapshot stack is bounded by hand length (~80 actions max).
- **Python socketio compatibility** with the React `socket.io-client`. Both follow the socket.io v4 protocol; should be drop-in. Verify in an early integration test.
