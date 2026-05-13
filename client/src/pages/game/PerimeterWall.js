import { hiddenTileUrl } from '../../sharedTiles';
import { drawFront, drawBack } from '../../api';
import './PerimeterWall.scss';

const STACKS = 18;
const LAYERS = 2;

function isHighlight(seat, stack, layer, target) {
  return target && target[0] === seat && target[1] === stack && target[2] === layer;
}

function WallSide({ seat, sideClass, frontPos, backPos, presentSet, canDrawFront, canDrawBack }) {
  return (
    <div className={`perimeter-wall-side ${sideClass}`}>
      {Array.from({ length: STACKS }, (_, stack) => (
        <div className="stack" key={stack}>
          {Array.from({ length: LAYERS }, (_, layer) => {
            const present = presentSet.has(`${seat},${stack},${layer}`);
            if (!present) return <div key={layer} className="wall-slot empty" />;
            const isFront = isHighlight(seat, stack, layer, frontPos) && canDrawFront;
            const isBack = isHighlight(seat, stack, layer, backPos) && canDrawBack;
            const clickable = isFront || isBack;
            const cls = isFront
              ? 'wall-slot highlight front clickable'
              : isBack
              ? 'wall-slot highlight back clickable'
              : 'wall-slot';
            return (
              <img
                key={layer}
                className={cls}
                src={hiddenTileUrl()}
                alt=""
                onClick={clickable ? (isFront ? () => drawFront() : () => drawBack()) : undefined}
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
  const canDrawFront = state.available_actions.includes('draw_front');
  const canDrawBack = state.available_actions.includes('draw_back');
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
          frontPos={wall.next_front_position}
          backPos={wall.next_back_position}
          presentSet={presentSet}
          canDrawFront={canDrawFront}
          canDrawBack={canDrawBack}
        />
      ))}
    </div>
  );
}
