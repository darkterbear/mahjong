import { useEffect, useRef } from 'react';
import { tileImageUrl } from '../../sharedTiles';
import './EventLog.scss';

const ACTION_LABELS = {
  draw_front: 'drew',
  draw_back: 'drew (replacement)',
  discard: 'discarded',
  declare_flower: 'declared flower',
  peng: 'pong',
  chi: 'chi',
  gang_open: 'kong',
  gang_concealed: 'concealed kong',
  gang_added: 'added kong',
  hu: 'won',
  robbing_kong_hu: 'won by robbing kong',
};

function nameFor(seat, state) {
  if (state.you.seat === seat) return state.you.username || 'You';
  const o = state.others.find((o) => o.seat === seat);
  return o ? o.username : `Seat ${seat}`;
}

function renderTiles(e) {
  if (e.kind === 'chi' && Array.isArray(e.with_tiles) && e.with_tiles.length === 2) {
    const sorted = [...e.with_tiles].sort((a, b) => a - b);
    const display = [sorted[0], e.tile, sorted[1]];
    return (
      <span className="event-tiles">
        {display.map((tid, j) => (
          <img key={j} className="event-tile chi-tile" src={tileImageUrl(tid)} alt="" />
        ))}
      </span>
    );
  }
  if (e.tile !== undefined && e.tile != null) {
    return <img className="event-tile" src={tileImageUrl(e.tile)} alt="" />;
  }
  return null;
}

export function EventLog({ state }) {
  const containerRef = useRef(null);
  const events = state.event_log || [];

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [events.length]);

  return (
    <div className="event-log">
      <h4>Event log</h4>
      <div className="event-log-scroll" ref={containerRef}>
        {events.map((e, i) => (
          <div key={i} className="event-line">
            <span className="event-actor">{nameFor(e.seat, state)}</span>
            <span className="event-verb"> {ACTION_LABELS[e.kind] || e.kind} </span>
            {renderTiles(e)}
          </div>
        ))}
      </div>
    </div>
  );
}
