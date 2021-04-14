import Player from './Player';
import Tile from './Tile';
import { randomCode } from '../utils';
import ActionIntent from './ActionIntent';
export default class Room {
  code: string;
  players: Player[];
  leader?: Player;
  deck: Tile[];
  turn: number;
  pendingAction?: ActionIntent;

  private static rooms: Map<string, Room> = new Map();

  /**
   * Generates a unique room code.
   * @returns 
   */
  static generateCode(): string {
    const existingCodes = new Set(this.rooms.keys());

    let code;
    do code = randomCode(); while (existingCodes.has(code));

    return code;
  }

  /**
   * Fetches a room from the server state by code.
   * @param code 
   * @returns 
   */
  static getRoom(code: string): Room | undefined {
    return Room.rooms.get(code);
  }

  /**
   * Creates a new Room object, and added to the server state.
   */
  constructor() {
    this.code = Room.generateCode();
    this.players = [];
    this.deck = [];
    this.turn = -1;

    Room.rooms.set(this.code, this);
  }

  /**
   * Returns whether or not the room has a game in progress (deck has tiles)
   */
  inGame(): boolean {
    return this.deck.length > 0 || this.players.some(p => p.handConcealed.length + p.handExposed.length > 0);
  }

  /**
   * Returns a list of usernames of players in this room
   * @returns 
   */
  playerNames(): string[] {
    return this.players.map(p => p.username);
  }

  /**
   * Removes this room from the server state. Room must be empty prior to destroying.
   */
  destroy(): void {
    if (this.players.length > 0) {
      throw new Error('Cannot destroy non-empty room');
    }

    Room.rooms.delete(this.code);
  }

  /**
   * Sets turn to next player, draws a tile for them.
   */
  nextTurn(): void {
    this.turn = (this.turn + 1) % 4;
    this.players[this.turn].handConcealed.push(this.deck.pop());
  }

  /**
   * Emits a game state update to all players in the room.
   */
  emitUpdates(): void {
    for (const p of this.players) {
      p.socket?.emit('game_state_update', p.getPerspectiveGameState());
    }
  }
}