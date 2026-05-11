import { hiddenTileUrl } from '../../sharedTiles';
import './PerimeterWall.scss';

const STACKS = 18;
const LAYERS = 2;

function isHighlight(seat, stack, layer, target) {
  return target && target[0] === seat && target[1] === stack && target[2] === layer;
}

function WallSide({ seat, sideClass, viewerSeat, frontPos, backPos }) {
  // Render 18 stacks, each 2 layers. Top layer rendered first (visible).
  return (
    <div className={`perimeter-wall-side ${sideClass}`}>
      {Array.from({ length: STACKS }, (_, stack) => (
        <div className="stack" key={stack}>
          {Array.from({ length: LAYERS }, (_, layer) => (
            <img
              key={layer}
              className={
                isHighlight(seat, stack, layer, frontPos)
                  ? 'wall-tile highlight front'
                  : isHighlight(seat, stack, layer, backPos)
                  ? 'wall-tile highlight back'
                  : 'wall-tile'
              }
              src={hiddenTileUrl()}
              alt=""
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function PerimeterWall({ state }) {
  const yourSeat = state.you.seat;
  const wall = state.wall;
  // Decide whether the next-draw indicator is FRONT or BACK based on the
  // viewer's own available_actions.
  const showBack = state.available_actions.includes('draw_back');
  const target = showBack ? wall.next_back_position : wall.next_front_position;

  // Map physical seat index → which CSS side from viewer's POV.
  const side = (seat) => {
    const offset = (seat - yourSeat + 4) % 4;
    return ['bottom', 'right', 'top', 'left'][offset];
  };

  return (
    <div className="perimeter-wall">
      {[0, 1, 2, 3].map((seat) => (
        <WallSide
          key={seat}
          seat={seat}
          sideClass={side(seat)}
          viewerSeat={yourSeat}
          frontPos={!showBack ? wall.next_front_position : null}
          backPos={showBack ? wall.next_back_position : null}
        />
      ))}
    </div>
  );
}
