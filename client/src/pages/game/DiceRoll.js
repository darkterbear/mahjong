import './DiceRoll.scss';

// Pip positions on a standard die for each face value 1-6, expressed as
// row/column indices on a 3×3 grid (rows top→bottom, cols left→right).
const PIP_POSITIONS = {
  1: [[1, 1]],
  2: [[0, 0], [2, 2]],
  3: [[0, 0], [1, 1], [2, 2]],
  4: [[0, 0], [0, 2], [2, 0], [2, 2]],
  5: [[0, 0], [0, 2], [1, 1], [2, 0], [2, 2]],
  6: [[0, 0], [0, 2], [1, 0], [1, 2], [2, 0], [2, 2]],
};

function Die({ value }) {
  const positions = PIP_POSITIONS[value] || [];
  const present = new Set(positions.map(([r, c]) => `${r},${c}`));
  // Render a 3×3 grid; each cell either has a pip dot or is empty.
  const cells = [];
  for (let r = 0; r < 3; r += 1) {
    for (let c = 0; c < 3; c += 1) {
      const filled = present.has(`${r},${c}`);
      cells.push(
        <span
          key={`${r}-${c}`}
          className={`pip ${filled ? 'on' : ''}`}
        />
      );
    }
  }
  return <div className="die">{cells}</div>;
}

export function DiceRoll({ dice }) {
  const sum = dice.d1 + dice.d2 + dice.d3;
  return (
    <div className="dice-roll">
      <div className="dice-row">
        <Die value={dice.d1} />
        <Die value={dice.d2} />
        <Die value={dice.d3} />
      </div>
      <div className="sum">{sum}</div>
      <p>Break at seat {dice.break_seat}, offset {dice.break_offset}</p>
    </div>
  );
}
