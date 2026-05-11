import { useState } from 'react';
import {
  rollDice, drawFront, drawBack, claim,
  declareConcealedGang, declareAddedGang, declareSelfHu, undo, nextHand,
  socket,
} from '../../api';
import { tileImageUrl } from '../../sharedTiles';
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
  co_hu_pass: 'Pass',
};

export function ActionBar({ state }) {
  const [picker, setPicker] = useState(null); // 'concealed' | 'added' | null
  const actions = state.available_actions || [];
  const buttons = actions.filter(
    (a) => !['discard', 'declare_flower'].includes(a)
  );
  const isCurrentSeat = state.current_turn_seat === state.you.seat;
  const showSelfHu = actions.includes('hu') && isCurrentSeat;

  const handleClick = (a) => {
    switch (a) {
      case 'roll_dice': return rollDice();
      case 'draw_front': return drawFront();
      case 'draw_back': return drawBack();
      case 'hu': {
        if (state.pending_co_hu && state.pending_co_hu.remaining_seats.includes(state.you.seat)) {
          return socket.emit('co_hu_response', { accept: true });
        }
        return showSelfHu ? declareSelfHu() : claim('hu');
      }
      case 'co_hu_pass': return socket.emit('co_hu_response', { accept: false });
      case 'peng': return claim('peng');
      case 'chi': return claim('chi');  // chi disambiguation deferred
      case 'gang_open': return claim('gang_open');
      case 'declare_concealed_gang': return setPicker('concealed');
      case 'declare_added_gang': return setPicker('added');
      case 'next_hand': return nextHand();
      default: return null;
    }
  };

  const eligibleTiles = picker === 'concealed'
    ? (state.you.concealed_gang_tiles || [])
    : picker === 'added'
    ? (state.you.added_gang_tiles || [])
    : [];

  const onPickTile = (tile_id) => {
    if (picker === 'concealed') declareConcealedGang(tile_id);
    else if (picker === 'added') declareAddedGang(tile_id);
    setPicker(null);
  };

  return (
    <div className="action-bar">
      {!picker && (
        <>
          {buttons.map((a) => (
            <button key={a} onClick={() => handleClick(a)}>
              {LABELS[a] || a}
            </button>
          ))}
          {state.can_undo && (
            <button className="undo" onClick={() => undo()}>Undo</button>
          )}
        </>
      )}
      {picker && (
        <div className="kong-picker">
          <span className="picker-label">
            Pick a tile to {picker === 'concealed' ? 'concealed-kong' : 'add-kong'}:
          </span>
          {eligibleTiles.length === 0 ? (
            <span className="empty">(no eligible tiles)</span>
          ) : (
            eligibleTiles.map((tid) => (
              <img
                key={tid}
                className="picker-tile"
                src={tileImageUrl(tid)}
                onClick={() => onPickTile(tid)}
                alt=""
              />
            ))
          )}
          <button className="cancel" onClick={() => setPicker(null)}>Cancel</button>
        </div>
      )}
    </div>
  );
}
