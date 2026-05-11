import { nextHand } from '../../api';
import './SettlementModal.scss';

export function SettlementModal({ settlement, isNextDealer, onDismiss }) {
  const isDraw = settlement.is_draw || !settlement.winners || settlement.winners.length === 0;
  const headline = isDraw
    ? 'Draw — wall exhausted'
    : settlement.winners.length === 1
    ? `Seat ${settlement.winners[0].seat} wins!`
    : `Multi-winner: seats ${settlement.winners.map(w => w.seat).join(', ')}`;
  return (
    <div className="settlement-modal">
      <div className="modal-card">
        <h2>{headline}</h2>
        {!isDraw && (
          <>
            <p>Source: {settlement.source}</p>
            {settlement.winners.map((w) => (
              <div key={w.seat} className="winner-block">
                <h3>Seat {w.seat} (winning tile {w.winning_tile}) — total {w.total}</h3>
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
                <li key={i}>Seat {i}: {p >= 0 ? '+' : ''}{p}</li>
              ))}
            </ul>
            <h3>Cumulative</h3>
            <ul>
              {settlement.cumulative.map((c, i) => (
                <li key={i}>Seat {i}: {c >= 0 ? '+' : ''}{c}</li>
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
