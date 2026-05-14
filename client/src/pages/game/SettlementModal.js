import { useEffect, useState } from 'react';
import { nextHand } from '../../api';
import './SettlementModal.scss';

export function SettlementModal({ settlement, state, isNextDealer, onDismiss }) {
  const usernameFor = (seat) => {
    if (state && state.you.seat === seat) return state.you.username || 'You';
    const o = state && state.others.find((o) => o.seat === seat);
    return o ? o.username : `Seat ${seat}`;
  };
  const isDraw = settlement.is_draw || !settlement.winners || settlement.winners.length === 0;
  const headline = isDraw
    ? 'Draw — wall exhausted'
    : settlement.winners.length === 1
    ? `${usernameFor(settlement.winners[0].seat)} (seat ${settlement.winners[0].seat}) wins!`
    : `Multi-winner: ${settlement.winners.map((w) => `${usernameFor(w.seat)} (seat ${w.seat})`).join(', ')}`;

  // Countdown for auto-advance when the next dealer is a bot.
  const autoSec = settlement.auto_advance_seconds;
  const [remaining, setRemaining] = useState(
    autoSec != null ? Math.ceil(autoSec) : null
  );
  useEffect(() => {
    if (autoSec == null) return undefined;
    setRemaining(Math.ceil(autoSec));
    const startedAt = Date.now();
    const tick = setInterval(() => {
      const elapsed = (Date.now() - startedAt) / 1000;
      const r = Math.max(0, Math.ceil(autoSec - elapsed));
      setRemaining(r);
      if (r <= 0) clearInterval(tick);
    }, 250);
    return () => clearInterval(tick);
  }, [autoSec]);

  const sourceLabel =
    settlement.source === 'discard' && settlement.discarder_seat != null
      ? `Discard from ${usernameFor(settlement.discarder_seat)}`
      : settlement.source === 'discard'
      ? 'Discard'
      : settlement.source === 'self'
      ? 'Self-draw'
      : settlement.source;

  return (
    <div className="settlement-modal">
      <div className="modal-card">
        <h2>{headline}</h2>
        {!isDraw && (
          <>
            <p>Source: {sourceLabel}</p>
            {settlement.winners.map((w) => (
              <div key={w.seat} className="winner-block">
                <h3>{usernameFor(w.seat)} (seat {w.seat}) wins on tile {w.winning_tile} — total {w.total}</h3>
                <table>
                  <thead><tr><th>Tai</th><th>Pts</th></tr></thead>
                  <tbody>
                    {Object.entries(w.breakdown).map(([k, v]) => (
                      <tr key={k}><td>{k}</td><td>{v}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
            <h3>Payments this hand</h3>
            <ul>
              {settlement.payments.map((p, i) => (
                <li key={i}>{usernameFor(i)} (seat {i}): {p >= 0 ? '+' : ''}{p}</li>
              ))}
            </ul>
            <h3>Cumulative</h3>
            <ul>
              {settlement.cumulative.map((c, i) => (
                <li key={i}>{usernameFor(i)} (seat {i}): {c >= 0 ? '+' : ''}{c}</li>
              ))}
            </ul>
          </>
        )}
        {isNextDealer ? (
          <button onClick={() => { nextHand(); onDismiss(); }}>Next Hand</button>
        ) : remaining != null ? (
          <p className="auto-advance">
            Next hand starts in {remaining}s…
          </p>
        ) : (
          <p>Waiting for next dealer to advance…</p>
        )}
      </div>
    </div>
  );
}
