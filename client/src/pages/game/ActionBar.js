import { useState } from 'react';
import {
  rollDice, drawFront, drawBack, claim,
  declareConcealedGang, declareAddedGang, declareSelfHu, nextHand,
  claimDecision, claimWait,
} from '../../api';
import { tileImageUrl } from '../../sharedTiles';
import './ActionBar.scss';

function TimedButton({ children, onClick, durationSeconds, className }) {
  const animStyle = durationSeconds > 0
    ? { animationDuration: `${durationSeconds}s` }
    : { display: 'none' };
  return (
    <button className={`timed ${className || ''}`} onClick={onClick}>
      <span className="timer-fill" style={animStyle} />
      <span className="timer-label">{children}</span>
    </button>
  );
}

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

export function ActionBar({ state }) {
  const [picker, setPicker] = useState(null); // 'concealed' | 'added' | 'chi' | null
  const actions = state.available_actions || [];
  const buttons = actions.filter(
    (a) => !['discard', 'declare_flower'].includes(a)
  );
  const isCurrentSeat = state.current_turn_seat === state.you.seat;
  const showSelfHu = actions.includes('hu') && isCurrentSeat;

  const pcw = state.pending_claim_window;
  const inClaimWindow = pcw != null;
  const youDecided = pcw?.you_decided;
  const youWaiting = pcw?.you_waiting;
  const durationSeconds = pcw?.remaining_seconds || 0;
  const cwKey = pcw ? `${pcw.discarder_seat}-${pcw.tile}` : null;

  const handleClick = (a) => {
    switch (a) {
      case 'roll_dice': return rollDice();
      case 'draw_front': return drawFront();
      case 'draw_back': return drawBack();
      case 'hu': return showSelfHu ? declareSelfHu() : claim('hu');
      case 'peng': return claim('peng');
      case 'chi': return setPicker('chi');
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

  const chiCombos = picker === 'chi'
    ? (pcw?.chi_combos || [])
    : [];

  const onPickTile = (tile_id) => {
    if (picker === 'concealed') declareConcealedGang(tile_id);
    else if (picker === 'added') declareAddedGang(tile_id);
    setPicker(null);
  };

  const onPickChiCombo = (combo) => {
    claimDecision('chi', combo);
    setPicker(null);
  };

  // Claim window UI (viewer is not the discarder, and window is open).
  if (inClaimWindow && !picker) {
    if (youDecided) {
      return (
        <div className="action-bar">
          <span className="decided-indicator">Decided ✓</span>
        </div>
      );
    }

    const yourOptions = pcw?.your_options || [];

    const handleClaimWindowClick = (opt) => {
      if (opt === 'chi') {
        setPicker('chi');
      } else {
        claimDecision(opt);
      }
    };

    return (
      <div className="action-bar">
        {yourOptions.map((opt) => (
          <TimedButton
            key={`${opt}-${cwKey}`}
            durationSeconds={durationSeconds}
            onClick={() => handleClaimWindowClick(opt)}
          >
            {LABELS[opt] || opt}
          </TimedButton>
        ))}
        <TimedButton
          key={`pass-${cwKey}`}
          durationSeconds={durationSeconds}
          onClick={() => claimDecision('pass')}
        >
          Pass
        </TimedButton>
        <TimedButton
          key={`wait-${cwKey}`}
          durationSeconds={durationSeconds}
          className={youWaiting ? 'wait-active' : ''}
          onClick={() => claimWait(!youWaiting)}
        >
          {youWaiting ? 'Stop waiting' : 'Wait'}
        </TimedButton>
      </div>
    );
  }

  // Chi picker (within claim window).
  if (inClaimWindow && picker === 'chi') {
    return (
      <div className="action-bar">
        <div className="kong-picker">
          <span className="picker-label">Pick the two tiles to chi with:</span>
          {chiCombos.length === 0 ? (
            <span className="empty">(no chi combos)</span>
          ) : (
            chiCombos.map((combo, i) => (
              <span
                key={i}
                className="chi-combo"
                onClick={() => onPickChiCombo(combo)}
              >
                {combo.map((tid, j) => (
                  <img key={j} className="picker-tile" src={tileImageUrl(tid)} alt="" />
                ))}
              </span>
            ))
          )}
          <button className="cancel" onClick={() => setPicker(null)}>Cancel</button>
        </div>
      </div>
    );
  }

  // Normal turn UI (no claim window for this viewer).
  return (
    <div className="action-bar">
      {!picker && (
        <>
          {buttons.map((a) => (
            <button key={a} onClick={() => handleClick(a)}>
              {LABELS[a] || a}
            </button>
          ))}
        </>
      )}
      {picker && picker !== 'chi' && (
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
      {picker === 'chi' && (
        <div className="kong-picker">
          <span className="picker-label">Pick the two tiles to chi with:</span>
          {chiCombos.length === 0 ? (
            <span className="empty">(no chi combos)</span>
          ) : (
            chiCombos.map((combo, i) => (
              <span
                key={i}
                className="chi-combo"
                onClick={() => onPickChiCombo(combo)}
              >
                {combo.map((tid, j) => (
                  <img key={j} className="picker-tile" src={tileImageUrl(tid)} alt="" />
                ))}
              </span>
            ))
          )}
          <button className="cancel" onClick={() => setPicker(null)}>Cancel</button>
        </div>
      )}
    </div>
  );
}
