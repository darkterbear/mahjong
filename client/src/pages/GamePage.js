import { useEffect, useRef, useState } from 'react';
import { useHistory, useLocation } from 'react-router';
import { socket, authSocket } from '../api';
import { Scoreboard } from './game/Scoreboard';
import { PerimeterWall } from './game/PerimeterWall';
import { CenterDiscards } from './game/CenterDiscards';
import { PlayerSection } from './game/PlayerSection';
import { ActionBar } from './game/ActionBar';
import { SettlementModal } from './game/SettlementModal';
import { DiceRoll } from './game/DiceRoll';
import { EventLog } from './game/EventLog';
import './GamePage.scss';

export function GamePage() {
  const history = useHistory();
  const { code } = useLocation().state || {};

  const [state, setState] = useState(null);
  const [dice, setDice] = useState(null);
  const [settlement, setSettlement] = useState(null);
  const [dealing, setDealing] = useState(null);

  useEffect(() => {
    if (!socket) {
      history.replace('/');
      return;
    }
    if (code) authSocket(code);

    socket.on('state_update', (s) => setState(s));
    socket.on('dice_rolled', (d) => { setDice(d); setTimeout(() => setDice(null), 1500); });
    socket.on('dealing_step', (d) => setDealing(d));
    socket.on('hand_settlement', (s) => setSettlement(s));
    socket.on('disconnect', () => history.replace('/'));

    return () => {
      socket.off('state_update');
      socket.off('dice_rolled');
      socket.off('dealing_step');
      socket.off('hand_settlement');
      socket.off('disconnect');
    };
  }, []);

  useEffect(() => {
    if (state && state.phase !== 'SETTLEMENT' && settlement) {
      setSettlement(null);
    }
  }, [state?.phase]);

  // Click sound for tactile events (discard, chi, peng, gang variants).
  const clickAudio = useRef(null);
  const prevLogLen = useRef(0);
  useEffect(() => {
    if (!clickAudio.current) {
      clickAudio.current = new Audio('/sounds/click.wav');
      clickAudio.current.preload = 'auto';
    }
  }, []);
  useEffect(() => {
    const log = state?.event_log || [];
    if (log.length > prevLogLen.current) {
      const last = log[log.length - 1];
      const SOUND_KINDS = new Set([
        'discard', 'chi', 'peng',
        'gang_open', 'gang_concealed', 'gang_added',
      ]);
      if (last && SOUND_KINDS.has(last.kind) && clickAudio.current) {
        try {
          clickAudio.current.currentTime = 0;
          clickAudio.current.play().catch(() => { /* autoplay blocked until user gesture */ });
        } catch (_) {}
      }
    }
    prevLogLen.current = log.length;
  }, [state?.event_log?.length]);

  if (!state) {
    return <div id="game-page"><p>Connecting…</p></div>;
  }

  return (
    <div id="game-page">
      <header id="hand-header">
        <span>Round wind: <strong>{state.round_wind}</strong></span>
        <span>Dealer streak: <strong>{state.dealer_streak}</strong></span>
        <span style={{marginLeft: '2rem', color: '#aaa', fontSize: '12px'}}>
          phase=<strong>{state.phase}</strong> | turn=
          <strong>{state.current_turn_seat === state.you.seat ? 'YOU' : `seat ${state.current_turn_seat}`}</strong>
          {' | actions=['}
          <strong>{(state.available_actions || []).join(', ') || '(none)'}</strong>
          {']'}
        </span>
      </header>

      {state.pending_claim_window?.is_robbing_kong_window && (
        <div className="robbing-kong-banner">
          抢杠 — Rob the kong! Click Hu if you can win on this tile.
        </div>
      )}

      {state.pending_co_hu && state.pending_co_hu.remaining_seats.includes(state.you.seat) && (
        <div className="co-hu-banner">
          多家胡 — Co-Hu! Another player won on this tile. Click Hu to also win, or Pass.
        </div>
      )}

      <Scoreboard state={state} />
      <EventLog state={state} />

      <PerimeterWall state={state} />
      <CenterDiscards state={state} />

      <PlayerSection state={state} viewer="self" />
      {state.others.map((o) => (
        <PlayerSection key={o.seat} state={state} viewer={o.seat} other={o} />
      ))}

      <ActionBar state={state} />

      {dice && <DiceRoll dice={dice} />}

      {settlement && (
        <SettlementModal
          settlement={settlement}
          state={state}
          isNextDealer={state.you.seat === settlement.next_dealer_seat}
          onDismiss={() => setSettlement(null)}
        />
      )}
    </div>
  );
}
