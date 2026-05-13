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
    socket.on('dice_rolled', (d) => {
      setDice(d);
      setTimeout(() => setDice(null), 1500);
      // Tile-shuffle sound fires here (start of a new round).
      if (shuffleAudio.current && audioCtx.current) {
        try {
          const ctx = audioCtx.current;
          if (ctx.state === 'suspended') ctx.resume().catch(() => {});
          const buf = buffers.current.shuffle;
          if (buf) {
            const src = ctx.createBufferSource();
            src.buffer = buf;
            const gain = ctx.createGain();
            gain.gain.value = 2.0;
            src.connect(gain).connect(ctx.destination);
            src.start(0);
          }
        } catch (_) {}
      }
    });
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

  // Sound effects via Web Audio API so we can boost gain (the source wavs are
  // quieter than the UI calls for).
  const audioCtx = useRef(null);
  const buffers = useRef({});           // { click: AudioBuffer, shuffle: AudioBuffer }
  const prevLogLen = useRef(0);
  const prevPhase = useRef(null);

  const ensureContext = () => {
    if (!audioCtx.current) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      audioCtx.current = new Ctx();
    }
    if (audioCtx.current.state === 'suspended') {
      audioCtx.current.resume().catch(() => {});
    }
    return audioCtx.current;
  };

  const loadBuffer = (name, url) => {
    if (buffers.current[name]) return;
    const ctx = ensureContext();
    fetch(url)
      .then((r) => r.arrayBuffer())
      .then((ab) => ctx.decodeAudioData(ab))
      .then((buf) => { buffers.current[name] = buf; })
      .catch(() => {});
  };

  const playSound = (name, gainValue = 4.0) => {
    const ctx = ensureContext();
    const buf = buffers.current[name];
    if (!buf) return;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const gain = ctx.createGain();
    gain.gain.value = gainValue;
    src.connect(gain).connect(ctx.destination);
    try { src.start(0); } catch (_) {}
  };

  useEffect(() => {
    loadBuffer('click', '/sounds/click.wav');
    loadBuffer('shuffle', '/sounds/shuffle.wav');
    // Browsers require a user gesture before audio plays — install a one-shot
    // resume on the first pointerdown/keydown anywhere on the page.
    const unlock = () => {
      ensureContext();
      window.removeEventListener('pointerdown', unlock, true);
      window.removeEventListener('keydown', unlock, true);
    };
    window.addEventListener('pointerdown', unlock, true);
    window.addEventListener('keydown', unlock, true);
    return () => {
      window.removeEventListener('pointerdown', unlock, true);
      window.removeEventListener('keydown', unlock, true);
    };
  }, []);

  // (Shuffle sound is fired from the dice_rolled socket handler above.)

  // Play click on discards / claims.
  useEffect(() => {
    const log = state?.event_log || [];
    if (log.length > prevLogLen.current) {
      const last = log[log.length - 1];
      const SOUND_KINDS = new Set([
        'discard', 'chi', 'peng',
        'gang_open', 'gang_concealed', 'gang_added',
      ]);
      if (last && SOUND_KINDS.has(last.kind)) {
        playSound('click', 5.0);
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
