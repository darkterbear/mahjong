import { Tile } from 'mahjong';
import { Socket } from 'socket.io';
import Room from './Room';

export default class Player {
  id: string;
  username: string;
  room?: Room;
  handConcealed: Tile[];
  handExposed: Tile[][];
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
   * Adds tile to the player's discard pile
   */
  discard(tile: Tile): void {
    this.discarded.push(tile);
    this.discarded = this.discarded.slice(Math.max(0, this.discarded.length - 5));
  }

  /**
   * Forms a meld from an interrupt with the given tiles and adds to handExposed
   * @param tile Tile to chow/pong/kong
   * @param indices Indices of tiles in handConceal to meld with
   */
  takeMeld(tile: Tile, indices: number[]): void {
    // Remove index positions in reverse order to account for shifting
    const handTiles = indices.sort((a, b) => a - b).reverse().map(i => this.handConcealed.splice(i, 1)[0]);
    this.handExposed.push([tile, ...handTiles].sort(Tile.comparator));
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
   * Gets the index of the winner, from this player's perspective.
   */
  getPerspectiveWinner(): number {
    const thisIndex = this.room.players.indexOf(this);
    const roomWinner = this.room.winner;

    if (roomWinner < 0 || roomWinner > 3) return roomWinner;

    for (let i = 0; i < 4; i++) {
      if ((thisIndex + i + 1) % 4 === roomWinner) return i;
    }
  }

  /**
   * Gets the other players in perspective order (left is index 2, top is index 1, right is index 0)
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
      return null;
    }

    const result = {
      handConcealed: this.handConcealed,
      handExposed: this.handExposed,
      discarded: this.discarded,
      turn: this.getPerspectiveTurn(),
      winner: this.getPerspectiveWinner(),
      players: this.getPerspectivePlayers(),
    } as any;

    if (this.room.pendingAction) {
      result.pendingAction = {...(this.room.pendingAction as any)};
      delete result.pendingAction.timeout;
    }
    
    return result;
  }

  /**
   * Returns whether or not this player has a winning hand.
   */
  won(): boolean {
    return Tile.winningHand(this.handConcealed.slice().sort(Tile.comparator), 1, 4 - this.handExposed.length);
  }

  /**
   * Makes all tiles of this player visible
   * @param t Tile that this player wins with
   */
  win(t?: Tile): void {
    if (t) {
      this.handConcealed.concat(t);
    }

    this.handExposed.push(this.handConcealed);
    this.handConcealed = [];

    this.handExposed[this.handExposed.length - 1].sort(Tile.comparator);
  }
}
