import { tileImageUrl, hiddenTileUrl, isFlower } from '../../sharedTiles';
import { discard, declareFlower } from '../../api';
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
  const { hand, melds, flowers, drawn_tile, seat_wind } = state.you;
  const canDiscard = state.available_actions.includes('discard');
  const canDeclareFlower = state.available_actions.includes('declare_flower');

  const onTileClick = (tileId, indexInHand) => {
    if (canDeclareFlower && isFlower(tileId)) {
      declareFlower(tileId);
      return;
    }
    if (canDiscard) {
      discard(tileId);
    }
  };

  const drawnSet = drawn_tile != null ? [drawn_tile] : [];
  const handWithoutDrawn = drawn_tile != null
    ? (() => { const c = [...hand]; const i = c.lastIndexOf(drawn_tile); if (i >= 0) c.splice(i, 1); return c; })()
    : hand;

  return (
    <div className="player-section self">
      <div className="meta-row">
        <span className="seat-wind">{seat_wind}</span>
        <span className="flowers">{flowers.map((f, i) => tileImg(f, `f${i}`))}</span>
      </div>
      <div className="hand-row">
        {handWithoutDrawn.map((t, i) => tileImg(t, `h${i}`, () => onTileClick(t, i)))}
        {drawnSet.length > 0 && <span className="gap"></span>}
        {drawnSet.map((t, i) => tileImg(t, `d${i}`, () => onTileClick(t, i), 'drawn'))}
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
  return (
    <div className={`player-section other ${side}`}>
      <div className="meta-row">
        <span className="username">{other.username}</span>
        <span className="seat-wind">{other.seat_wind}</span>
        <span className="flowers">{other.flowers.map((f, i) => tileImg(f, `f${i}`))}</span>
      </div>
      <div className="hand-row hidden-hand">
        {Array.from({ length: other.hand_count }, (_, i) => (
          <img key={i} className="tile" src={hiddenTileUrl()} alt="" />
        ))}
        <span className="meld-row">
          {other.melds.map((m, i) => (
            <span key={i} className="meld">
              {m.tiles.map((t, j) => tileImg(t, `${i}-${j}`))}
            </span>
          ))}
        </span>
      </div>
      <div className="discards-row">
        {other.discards.map((t, i) => tileImg(t, `disc${i}`))}
      </div>
    </div>
  );
}
