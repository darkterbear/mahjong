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

  /**
   * Used to determine whether or not a hand is winning.
   * @param hand Available tiles to satisfy the requirements
   * @param pairsNeeded Number of pairs required
   * @param setsNeeded Number of pongs/kongs/chows required
   * @returns Whether or not the hand satisfiest he requirements
   */
  static winningHand(hand: Tile[], pairsNeeded: number, setsNeeded: number): boolean {
    if (pairsNeeded === 0 && setsNeeded === 0) return true;

    // Enumerate all possible pairs and triplets of tiles
    for (let i = 0; i < hand.length; i++) {
      for (let j = i + 1; j < hand.length; j++) {
        if (hand[i].suit !== hand[j].suit || Math.abs(hand[i].value - hand[j].value) > 2) continue;

        // Try pair i, j
        if (pairsNeeded > 0 
          && hand[i].value === hand[j].value 
          && Tile.winningHand(hand.filter((_, h) => h !== i && h !== j), pairsNeeded - 1, setsNeeded)) {
          return true;
        }

        if (setsNeeded > 0) {
          for (let k = j + 1; k < hand.length; k++) {
            if (hand[i].suit !== hand[k].suit
                || Math.abs(hand[k].value - hand[j].value) > 2
                || Math.abs(hand[k].value - hand[i].value) > 2
            ) {
              continue;
            }

            // Is this triplet all the same value or a run?
            if (
              (
                (hand[i].value === hand[j].value && hand[i].value === hand[k].value) 
                || (hand[j].value - hand[i].value === 1 && hand[k].value - hand[j].value === 1 && hand[i].suit !== Suit.DRAGON && hand[i].suit !== Suit.WIND)
              )
              && Tile.winningHand(hand.filter((_, h) => h !== i && h !== j && h !== k), pairsNeeded, setsNeeded - 1)) {
              return true;
            }
          }
        }
      }
    }

    return false;
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

