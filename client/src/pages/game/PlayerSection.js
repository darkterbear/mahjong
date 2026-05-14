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
  const isYourTurn = state.current_turn_seat === state.you.seat;

  const onTileClick = (tileId) => {
    if (canDiscard) {
      discard(tileId);
    }
  };

  // Render the full hand inline — no special positioning for the just-drawn tile.
  return (
    <div className="player-section self">
      <div className={`meta-row ${isYourTurn ? 'active-turn' : ''}`}>
        <span className="seat-wind">{seat_wind}</span>
      </div>
      <div className="hand-row">
        {hand.map((t, i) => tileImg(t, `h${i}`, () => onTileClick(t, i)))}
        {flowers.length > 0 && (
          <span className="flower-row">
            {flowers.map((f, i) => tileImg(f, `fl${i}`))}
          </span>
        )}
        <span className="meld-row">
          {melds.map((m, i) => (
            <span key={i} className="meld">
              {orderMeldTiles(m).map((t, j) => tileImg(t, `${i}-${j}`))}
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
  const isTheirTurn = state.current_turn_seat === other.seat;
  // When the server reveals the winner's hand (on settlement), `other.hand`
  // is populated — render the real tiles instead of the hidden backs.
  const revealedHand = other.hand;
  const hiddenCount = revealedHand
    ? 0
    : Math.max(0, other.hand_count - pending.length);
  return (
    <div className={`player-section other ${side}`}>
      <div className={`meta-row ${isTheirTurn ? 'active-turn' : ''}`}>
        <span className="username">{other.username}</span>
        <span className="seat-wind">{other.seat_wind}</span>
      </div>
      <div className={`hand-row ${revealedHand ? '' : 'hidden-hand'}`}>
        {revealedHand
          ? revealedHand.map((t, i) => tileImg(t, `r${i}`))
          : Array.from({ length: hiddenCount }, (_, i) => (
              <img key={`h${i}`} className="tile" src={hiddenTileUrl()} alt="" />
            ))}
        {!revealedHand && pending.map((f, i) => tileImg(f, `pf${i}`))}
        {other.flowers.length > 0 && (
          <span className="flower-row">
            {other.flowers.map((f, i) => tileImg(f, `fl${i}`))}
          </span>
        )}
        <span className="meld-row">
          {other.melds.map((m, i) => (
            <span key={i} className="meld">
              {m.concealed_hidden
                ? m.tiles.map((_, j) => (
                    <img
                      key={`${i}-${j}`}
                      className="tile"
                      src={hiddenTileUrl()}
                      alt=""
                    />
                  ))
                : orderMeldTiles(m).map((t, j) => tileImg(t, `${i}-${j}`))}
            </span>
          ))}
        </span>
      </div>
    </div>
  );
}

// For a chi meld, render the claimed (discarded) tile in the middle so it's
// visually distinct from the two tiles the claimer contributed.
function orderMeldTiles(meld) {
  if (meld.type === 'CHI' && meld.source_tile != null && meld.tiles.length === 3) {
    const claimed = meld.source_tile;
    const own = meld.tiles.filter((t) => t !== claimed);
    if (own.length === 2) {
      own.sort((a, b) => a - b);
      return [own[0], claimed, own[1]];
    }
    // Handles the edge case where the claimed tile id appears in `own` too
    // (would only happen with bad data); fall back to original order.
  }
  return meld.tiles;
}
