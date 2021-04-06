import InterruptingAction from '@game/InterruptingAction';
import Player from '@game/Player';
import Tile from '@game/Tile';

export default class Room {
  players: Player[];
  leader: Player;
  deck: Tile[];
  turn: number;
  pendingAction: InterruptingAction;
  timer?: NodeJS.Timeout;

  constructor(creator: Player) {
    this.players = [creator];
    this.leader = creator;
    this.deck = [];
    this.turn = -1;
    this.pendingAction = InterruptingAction.NONE;
  }
}