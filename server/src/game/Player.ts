import Tile from '@game/Tile';
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
}