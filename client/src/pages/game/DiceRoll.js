import './DiceRoll.scss';

export function DiceRoll({ dice }) {
  return (
    <div className="dice-roll">
      <div className="die">{dice.d1}</div>
      <div className="die">{dice.d2}</div>
      <div className="die">{dice.d3}</div>
      <p>Break at seat {dice.break_seat}, offset {dice.break_offset}</p>
    </div>
  );
}
