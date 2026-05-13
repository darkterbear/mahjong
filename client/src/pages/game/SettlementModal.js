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
    ? `${usernameFor(settlement.winners[0].seat)} wins!`
    : `Multi-winner: ${settlement.winners.map((w) => usernameFor(w.seat)).join(', ')}`;
  return (
    <div className="settlement-modal">
      <div className="modal-card">
        <h2>{headline}</h2>
        {!isDraw && (
          <>
            <p>Source: {settlement.source}</p>
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
        ) : (
          <p>Waiting for next dealer to advance…</p>
        )}
      </div>
    </div>
  );
}
