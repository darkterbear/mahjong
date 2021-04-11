export default class ActionIntent {
  username: string;
  action: Action;
  timeout: NodeJS.Timeout;
  executionTime: number;

  constructor(username: string, action: Action, timeout: NodeJS.Timeout, executionTime: number) {
    this.username = username;
    this.action = action;
    this.timeout = timeout;
    this.executionTime = executionTime;
  }
}

export enum Action {
  CHOW = 1,
  PONG = 2,
  MAHJONG = 3
}