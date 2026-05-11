import { nextHand } from '../../api';
import './SettlementModal.scss';

export function SettlementModal({ settlement, isNextDealer, onDismiss }) {
  const isDraw = settlement.winner_seat == null;
  return (
    <div className="settlement-modal">
      <div className="modal-card">
        <h2>{isDraw ? 'Draw — wall exhausted' : `Seat ${settlement.winner_seat} wins!`}</h2>
        {!isDraw && (
          <>
            <p>Source: {settlement.source}, Total: {settlement.total}</p>
            <table>
              <thead><tr><th>Tai</th><th>Pts</th></tr></thead>
              <tbody>
                {Object.entries(settlement.breakdown).map(([k, v]) => (
                  <tr key={k}><td>{k}</td><td>{v}</td></tr>
                ))}
              </tbody>
            </table>
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
