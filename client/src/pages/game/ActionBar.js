import {
  rollDice, drawFront, drawBack, claim,
  declareConcealedGang, declareAddedGang, declareSelfHu, undo, nextHand,
} from '../../api';
import './ActionBar.scss';

const LABELS = {
  roll_dice: 'Roll Dice',
  draw_front: 'Draw',
  draw_back: 'Draw (back)',
  hu: 'Hu!',
  peng: 'Peng',
  chi: 'Chi',
  gang_open: 'Kong',
  declare_concealed_gang: 'Concealed Kong',
  declare_added_gang: 'Add Kong',
  next_hand: 'Next Hand',
};

const HANDLERS = {
  roll_dice: () => rollDice(),
  draw_front: () => drawFront(),
  draw_back: () => drawBack(),
  hu: () => claim('hu'),
  peng: () => claim('peng'),
  chi: () => claim('chi'),  // chi-tile picker handled in a follow-up flow
  gang_open: () => claim('gang_open'),
  declare_concealed_gang: () => {
    const t = window.prompt('Tile id for concealed kong:');
    if (t != null) declareConcealedGang(parseInt(t, 10));
  },
  declare_added_gang: () => {
    const t = window.prompt('Tile id for added kong:');
    if (t != null) declareAddedGang(parseInt(t, 10));
  },
  next_hand: () => nextHand(),
};

export function ActionBar({ state }) {
  const actions = state.available_actions || [];
  // DISCARD / DECLARE_FLOWER are handled via tile clicks, not buttons.
  const buttons = actions.filter(
    (a) => !['discard', 'declare_flower'].includes(a)
  );

  const showSelfHu = actions.includes('hu') && state.current_turn_seat === state.you.seat;

  return (
    <div className="action-bar">
      {buttons.map((a) => (
        <button
          key={a}
          onClick={() => {
            if (a === 'hu' && showSelfHu) declareSelfHu();
            else HANDLERS[a]?.();
          }}
        >
          {LABELS[a] || a}
        </button>
      ))}
      {state.can_undo && (
        <button className="undo" onClick={() => undo()}>Undo</button>
      )}
    </div>
  );
}
