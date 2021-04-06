import Tile from '@game/Tile';

export default class Player {
  id: string;
  username: string;
  handConcealed: Tile[];
  handExposed: Tile[];
  discarded: Tile[];

  constructor(id: string, username: string) {
    this.id = id;
    this.username = username;
    this.handConcealed = [];
    this.handExposed = [];
    this.discarded = [];
  }
}