import Tile from './Tile';

export default class ActionIntent {
  username: string;
  action: Action;
  tile: Tile;
  timeout: NodeJS.Timeout;
  executionTime: number;

  constructor(username: string, action: Action, tile: Tile, timeout: NodeJS.Timeout, executionTime: number) {
    this.username = username;
    this.action = action;
    this.tile = tile;
    this.timeout = timeout;
    this.executionTime = executionTime;
  }
}

export enum Action {
  NONE = 0,
  CHOW = 1,
  PONG = 2,
  MAHJONG = 3
}