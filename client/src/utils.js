/**
   * Copied from server/src/game/Tile.ts
   * Used to determine whether or not a hand is winning.
   * @param hand Available tiles to satisfy the requirements
   * @param pairsNeeded Number of pairs required
   * @param setsNeeded Number of pongs/kongs/chows required
   * @returns Whether or not the hand satisfiest he requirements
   */
export const winningHand = (hand, pairsNeeded, setsNeeded) => {
  if (pairsNeeded === 0 && setsNeeded === 0) return true;

  // Enumerate all possible pairs and triplets of tiles
  for (let i = 0; i < hand.length; i++) {
    for (let j = i + 1; j < hand.length; j++) {
      if (hand[i].suit !== hand[j].suit || Math.abs(hand[i].value - hand[j].value) > 2) continue;

      // Try pair i, j
      if (pairsNeeded > 0 
        && hand[i].value === hand[j].value 
        && winningHand(hand.filter((_, h) => h !== i && h !== j), pairsNeeded - 1, setsNeeded)) {
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
              || (hand[j].value - hand[i].value === 1 && hand[k].value - hand[j].value === 1 && hand[i].suit !== 'd' && hand[i].suit !== 'f')
            )
            && winningHand(hand.filter((_, h) => h !== i && h !== j && h !== k), pairsNeeded, setsNeeded - 1)) {
            return true;
          }
        }
      }
    }
  }

  return false;
}
