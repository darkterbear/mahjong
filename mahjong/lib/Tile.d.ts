export declare enum Suit {
    DRAGON = "d",
    WIND = "f",
    BAMBOO = "s",
    DOTS = "t",
    WAN = "w"
}
export default class Tile {
    suit: Suit;
    value: number;
    constructor(suit: Suit, value: number);
    static comparator(a: Tile, b: Tile): number;
    /**
     * Used to determine whether or not a hand is winning.
     * @param hand Available tiles to satisfy the requirements
     * @param pairsNeeded Number of pairs required
     * @param setsNeeded Number of pongs/kongs/chows required
     * @returns Whether or not the hand satisfiest he requirements
     */
    static winningHand(hand: Tile[], pairsNeeded: number, setsNeeded: number): boolean;
    static isSameSuit(tiles: Tile[]): boolean;
    static isChow(t1: Tile, t2: Tile, t3: Tile): boolean;
    static isPong(tiles: Tile[]): boolean;
    static shuffledDeck(): Tile[];
}
