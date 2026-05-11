import { tileImageUrl, hiddenTileUrl } from '../../sharedTiles';
import { discard } from '../../api';
import './PlayerSection.scss';

function tileImg(tileId, key, onClick, extraClass = '') {
  return (
    <img
      key={key}
      className={`tile ${extraClass}`}
      src={tileImageUrl(tileId)}
      onClick={onClick}
      alt=""
    />
  );
}

export function PlayerSection({ state, viewer, other }) {
  if (viewer === 'self') return <SelfSection state={state} />;
  return <OtherSection state={state} other={other} />;
}

function SelfSection({ state }) {
  const { hand, melds, flowers, seat_wind } = state.you;
  const canDiscard = state.available_actions.includes('discard');

  const onTileClick = (tileId) => {
    if (canDiscard) {
      discard(tileId);
    }
  };

  // Render the full hand inline — no special positioning for the just-drawn tile.
  return (
    <div className="player-section self">
      <div className="meta-row">
        <span className="seat-wind">{seat_wind}</span>
        <span className="flowers">{flowers.map((f, i) => tileImg(f, `f${i}`))}</span>
      </div>
      <div className="hand-row">
        {hand.map((t, i) => tileImg(t, `h${i}`, () => onTileClick(t, i)))}
        <span className="meld-row">
          {melds.map((m, i) => (
            <span key={i} className="meld">
              {m.tiles.map((t, j) => tileImg(t, `${i}-${j}`))}
            </span>
          ))}
        </span>
      </div>
    </div>
  );
}

function OtherSection({ state, other }) {
  const offset = (other.seat - state.you.seat + 4) % 4;
  const side = ['', 'right', 'top', 'left'][offset];
  const pending = other.pending_flowers || [];
  const hiddenCount = Math.max(0, other.hand_count - pending.length);
  return (
    <div className={`player-section other ${side}`}>
      <div className="meta-row">
        <span className="username">{other.username}</span>
        <span className="seat-wind">{other.seat_wind}</span>
        <span className="flowers">{other.flowers.map((f, i) => tileImg(f, `f${i}`))}</span>
      </div>
      <div className="hand-row hidden-hand">
        {Array.from({ length: hiddenCount }, (_, i) => (
          <img key={`h${i}`} className="tile" src={hiddenTileUrl()} alt="" />
        ))}
        {pending.map((f, i) => tileImg(f, `pf${i}`))}
        <span className="meld-row">
          {other.melds.map((m, i) => (
            <span key={i} className="meld">
              {m.tiles.map((t, j) => tileImg(t, `${i}-${j}`))}
            </span>
          ))}
        </span>
      </div>
    </div>
  );
}
