import { tileImageUrl } from '../../sharedTiles';
import './CenterDiscards.scss';

export function CenterDiscards({ state }) {
  // Build a discard quadrant per player. The viewer's discard pile sits at
  // the bottom of the center (closest to the viewer); counterclockwise
  // through right, top, left.
  const yourSeat = state.you.seat;
  const youDiscards = (state.you.discards || []);
  const piles = [
    { seat: yourSeat, side: 'bottom', discards: youDiscards },
    ...state.others.map((o) => {
      const offset = (o.seat - yourSeat + 4) % 4;
      const side = ['', 'right', 'top', 'left'][offset];
      return { seat: o.seat, side, discards: o.discards || [] };
    }),
  ];
  return (
    <div className="center-discards">
      {piles.map((p) => (
        <div key={p.seat} className={`pile pile-${p.side}`}>
          {p.discards.map((t, i) => (
            <img key={i} className="discard-tile" src={tileImageUrl(t)} alt="" />
          ))}
        </div>
      ))}
    </div>
  );
}
