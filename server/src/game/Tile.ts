export enum Suit {
  DRAGON = 'd',
  WIND = 'f',
  BAMBOO = 's',
  DOTS = 't',
  WAN = 'w'
}

export default class Tile {
  suit: Suit;
  value: number;

  constructor(suit: Suit, value: number) {
    this.suit = suit;
    this.value = value;
  }

  static comparator(a: Tile, b: Tile): number {
    if (a.suit !== b.suit) return 'stwfd'.indexOf(a.suit) - 'stwfd'.indexOf(b.suit);
    return a.value - b.value;
  }

  static shuffledDeck(): Tile[] {
    const deck = masterDeck.slice();

    // Shuffle
    for (let i = 0; i < deck.length; i++) {

      // choose a random not-yet-placed item to place there
      // must be an item AFTER the current item, because the stuff
      // before has all already been placed
      
      const r = Math.floor(Math.random() * (deck.length - i) + i);

      // place our random choice in the spot by swapping
      [deck[i], deck[r]] = [deck[r], deck[i]];
    }

    return deck;
  }
}

// Deck filled with singleton tiles
const masterDeck: Tile[] = [];
for (let copy = 0; copy < 4; copy++) {
  for (let i = 1; i < 10; i++) {
    masterDeck.push(new Tile(Suit.BAMBOO, i));
    masterDeck.push(new Tile(Suit.DOTS, i));
    masterDeck.push(new Tile(Suit.WAN, i));
  }
  
  for (let i = 1; i < 5; i++) {
    masterDeck.push(new Tile(Suit.WIND, i));
  }
  
  for (let i = 1; i < 4; i++) {
    masterDeck.push(new Tile(Suit.DRAGON, i));
  }
}

