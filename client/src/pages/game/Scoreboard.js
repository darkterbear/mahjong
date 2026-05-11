import './Scoreboard.scss';

export function Scoreboard({ state }) {
  const seats = [state.you, ...state.others.map((o) => ({ ...o, hand: null }))];
  return (
    <aside className="scoreboard">
      <h3>Scores</h3>
      <ul>
        {seats.map((s) => (
          <li key={s.seat}>
            <span className="name">{s.username || 'You'}</span>
            <span className="wind">{s.seat_wind}</span>
            <span className={`score ${s.score >= 0 ? 'pos' : 'neg'}`}>{s.score >= 0 ? '+' : ''}{s.score}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
