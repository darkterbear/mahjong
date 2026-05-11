import { hiddenTileUrl } from '../../sharedTiles';
import './PerimeterWall.scss';

const STACKS = 18;
const LAYERS = 2;

function isHighlight(seat, stack, layer, target) {
  return target && target[0] === seat && target[1] === stack && target[2] === layer;
}

function WallSide({ seat, sideClass, frontPos, backPos, presentSet }) {
  return (
    <div className={`perimeter-wall-side ${sideClass}`}>
      {Array.from({ length: STACKS }, (_, stack) => (
        <div className="stack" key={stack}>
          {Array.from({ length: LAYERS }, (_, layer) => {
            const present = presentSet.has(`${seat},${stack},${layer}`);
            if (!present) return <div key={layer} className="wall-slot empty" />;
            const className = isHighlight(seat, stack, layer, frontPos)
              ? 'wall-slot highlight front'
              : isHighlight(seat, stack, layer, backPos)
              ? 'wall-slot highlight back'
              : 'wall-slot';
            return (
              <img
                key={layer}
                className={className}
                src={hiddenTileUrl()}
                alt=""
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function PerimeterWall({ state }) {
  const yourSeat = state.you.seat;
  const wall = state.wall;
  const presentSet = new Set(
    (wall.remaining_positions || []).map((p) => `${p[0]},${p[1]},${p[2]}`)
  );
  const showBack = state.available_actions.includes('draw_back');
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
          frontPos={!showBack ? wall.next_front_position : null}
          backPos={showBack ? wall.next_back_position : null}
          presentSet={presentSet}
        />
      ))}
    </div>
  );
}
