import { useEffect, useState } from 'react';
import { useHistory, useLocation } from 'react-router';
import { socket, authSocket } from '../api';
import { Scoreboard } from './game/Scoreboard';
import { PerimeterWall } from './game/PerimeterWall';
import { PlayerSection } from './game/PlayerSection';
import { ActionBar } from './game/ActionBar';
import { SettlementModal } from './game/SettlementModal';
import { DiceRoll } from './game/DiceRoll';
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

  if (!state) {
    return <div id="game-page"><p>Connecting…</p></div>;
  }

  return (
    <div id="game-page">
      <header id="hand-header">
        <span>Round wind: <strong>{state.round_wind}</strong></span>
        <span>Dealer streak: <strong>{state.dealer_streak}</strong></span>
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

      <PerimeterWall state={state} />

      <PlayerSection state={state} viewer="self" />
      {state.others.map((o) => (
        <PlayerSection key={o.seat} state={state} viewer={o.seat} other={o} />
      ))}

      <ActionBar state={state} />

      {dice && <DiceRoll dice={dice} />}

      {settlement && (
        <SettlementModal
          settlement={settlement}
          isNextDealer={state.you.seat === settlement.next_dealer_seat}
          onDismiss={() => setSettlement(null)}
        />
      )}
    </div>
  );
}
