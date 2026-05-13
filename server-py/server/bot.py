"""Bot agent: loads subterfuge model + picks action indices via the neural network."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from subterfuge.engine.game import Game

# Lazily loaded on first use so the server starts even without torch installed.
_MODEL = None
_DEVICE = None

MODEL_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "subterfuge"
    / "checkpoints"
    / "run_20260510_222227"
    / "model_iter_4050.pt"
)


def _get_model():
    global _MODEL, _DEVICE
    if _MODEL is None:
        try:
            from subterfuge.model.utils import load_model, get_device
        except ImportError as exc:
            raise RuntimeError(
                "torch / subterfuge not importable — install torch to enable bot play"
            ) from exc
        _DEVICE = get_device()
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Bot model checkpoint not found: {MODEL_PATH}"
            )
        _MODEL, _meta = load_model(str(MODEL_PATH), device=_DEVICE)
        _MODEL.eval()
        print(f"[bot] model loaded from {MODEL_PATH}", file=sys.stderr)
    return _MODEL, _DEVICE


def choose_action_index(game: "Game", seat: int) -> int:
    """Return the discrete action index the model selects for *seat*.

    Uses argmax (deterministic) with a legal-action fallback if the top-logit
    action is masked out.
    """
    import numpy as np
    import torch
    from subterfuge.env.action_space import get_action_mask
    from subterfuge.env.observation import encode_observation

    tiles_np, scalars_np = encode_observation(game, seat)
    mask_np = get_action_mask(game, seat)

    model, device = _get_model()
    tiles_t = torch.from_numpy(tiles_np).unsqueeze(0).to(device)
    scalars_t = torch.from_numpy(scalars_np).unsqueeze(0).to(device)
    mask_t = torch.from_numpy(mask_np).unsqueeze(0).to(device)

    with torch.inference_mode():
        policy_logits, _value = model(tiles_t, scalars_t, action_mask=mask_t)

    action_idx = int(policy_logits.argmax(dim=-1).item())

    if not mask_np[action_idx]:
        # Fallback: highest-logit legal action.
        masked = policy_logits.squeeze(0).cpu().numpy().copy()
        masked[~mask_np] = -1e30
        action_idx = int(np.argmax(masked))

    return action_idx
