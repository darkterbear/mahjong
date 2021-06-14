import Tile, { Suit } from './Tile';

describe('Mahjong winning logic', () => {
  test('Winning hand single suit', () => {
    const hand: Tile[] = [
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 3),
      new Tile(Suit.BAMBOO, 4),
      new Tile(Suit.BAMBOO, 5),
      new Tile(Suit.BAMBOO, 6),
      new Tile(Suit.BAMBOO, 7),
      new Tile(Suit.BAMBOO, 8),
      new Tile(Suit.BAMBOO, 9),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 2),
    ];

    expect(Tile.winningHand(hand, 1, 4)).toBeTruthy();
  });

  test('Winning hand multiple suits', () => {
    const hand: Tile[] = [
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 3),
      new Tile(Suit.DOTS, 4),
      new Tile(Suit.DOTS, 5),
      new Tile(Suit.DOTS, 6),
      new Tile(Suit.WAN, 7),
      new Tile(Suit.WAN, 8),
      new Tile(Suit.WAN, 9),
      new Tile(Suit.WIND, 2),
      new Tile(Suit.WIND, 2),
      new Tile(Suit.WIND, 2),
    ];

    expect(Tile.winningHand(hand, 1, 4)).toBeTruthy();
  });

  test('No dragon runs', () => {
    const hand: Tile[] = [
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 1),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 3),
      new Tile(Suit.BAMBOO, 4),
      new Tile(Suit.BAMBOO, 5),
      new Tile(Suit.BAMBOO, 6),
      new Tile(Suit.DRAGON, 7),
      new Tile(Suit.DRAGON, 8),
      new Tile(Suit.DRAGON, 9),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 2),
      new Tile(Suit.BAMBOO, 2),
    ];

    expect(Tile.winningHand(hand, 1, 4)).toBeFalsy();
  });
});