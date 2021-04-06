export default class Tile {
  suit: Suit;
  value: number;

  constructor(suit: Suit, value: number) {
    this.suit = suit;
    this.value = value;
  }
}

export enum Suit {
  DRAGON,
  WIND,
  BAMBOO,
  DOTS,
  WAN
}