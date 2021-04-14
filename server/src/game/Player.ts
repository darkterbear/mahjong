import Tile from './Tile';
import { Socket } from 'socket.io';
import Room from './Room';

export default class Player {
  id: string;
  username: string;
  room?: Room;
  handConcealed: Tile[];
  handExposed: Tile[];
  discarded: Tile[];
  socket?: Socket;

  private static players: Map<string, Player> = new Map();

  /**
   * Fetches a player from the server state by ID.
   * @param id 
   * @returns 
   */
  static getPlayer(id: string): Player | undefined {
    return this.players.get(id);
  }

  /**
   * Creates a new Player object, and added to the server state.
   */
  constructor(id: string, username: string) {
    this.id = id;
    this.username = username;
    this.handConcealed = [];
    this.handExposed = [];
    this.discarded = [];

    Player.players.set(id, this);
  }

  /**
   * Joins the player into the room. Sets the room field of the player, and adds the player to the player list in the room.
   * @param room 
   */
  joinRoom(room: Room): void {
    this.room = room;
    room.players.push(this);

    if (!room.leader) {
      room.leader = this;
    }
  }

  /**
   * Removes this player from any room it is in, and the server state. Reassigns leader or destroys the room as necessary.
   */
  destroy(): void {
    const room = this.room;

    if (room) {
      // Remove this player
      room.players = room.players.filter(p => p !== this);

      if (room.players.length === 0) {
        // Destroy the room
        room.destroy();
      } else if (room.leader === this) {
        // Reassign leader
        room.leader = room.players[0];
      }
    }
    
    Player.players.delete(this.id);
  }

  /**
   * Discards a tile from their handConcealed, updates the discard pile
   * @param index Index of tile in handConcealed to discard
   */
  discard(index: number): void {
    if (!this.handConcealed[index]) return;
    this.discarded.push(this.handConcealed.splice(index, 1)[0]);
    this.discarded = this.discarded.slice(Math.max(0, this.discarded.length - 5));
  }

  /**
   * Gets the index of the player whose current turn it is, from this player's perspective.
   */
  getPerspectiveTurn(): number {
    const thisIndex = this.room.players.indexOf(this);
    const roomTurn = this.room.turn;

    for (let i = 0; i < 4; i++) {
      if ((thisIndex + i + 1) % 4 === roomTurn) return i;
    }
  }

  /**
   * Gets the other players in perspective order (left is index 0, top is index 1, right is index 2)
   */
  getPerspectivePlayers(): any[] {
    const thisIndex = this.room.players.indexOf(this);
    return this.room.players.slice(thisIndex + 1)
      .concat(this.room.players.slice(0, thisIndex))
      .map(p => ({ 
        username: p.username, 
        handExposed: p.handExposed, 
        discarded: p.discarded, 
      }));
  }

  /**
   * Gets this player's perspective of the game state:
   * {
   *    handConcealed: Tile[],
   *    handExposed: Tile[],
   *    discarded: Tile[],
   *    turn: number,
   *    pendingAction: ActionIntent (without the timer portion),
   *    players: {
   *      username: string,
   *      handExposed: Tile[],
   *      discarded: Tile[]
   *    }
   * }
   */
  getPerspectiveGameState(): any {
    if (!this.room || !this.room.inGame()) {
      throw new Error('Cannot get game state; player not in room, or room not in game');
    }

    const result = {
      handConcealed: this.handConcealed,
      handExposed: this.handExposed,
      discarded: this.discarded,
      turn: this.getPerspectiveTurn(),
      pendingAction: this.room.pendingAction as any,
      players: this.getPerspectivePlayers(),
    };

    if (result.pendingAction) {
      delete result.pendingAction.timeout;
    }
    
    return result;
  }
}