"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    Object.defineProperty(o, k2, { enumerable: true, get: function() { return m[k]; } });
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
Object.defineProperty(exports, "__esModule", { value: true });
const Tile_1 = __importStar(require("./Tile"));
describe('Mahjong winning logic', () => {
    test('Winning hand single suit', () => {
        const hand = [
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 3),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 4),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 5),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 6),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 7),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 8),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 9),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
        ];
        expect(Tile_1.default.winningHand(hand, 1, 4)).toBeTruthy();
    });
    test('Winning hand multiple suits', () => {
        const hand = [
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 3),
            new Tile_1.default(Tile_1.Suit.DOTS, 4),
            new Tile_1.default(Tile_1.Suit.DOTS, 5),
            new Tile_1.default(Tile_1.Suit.DOTS, 6),
            new Tile_1.default(Tile_1.Suit.WAN, 7),
            new Tile_1.default(Tile_1.Suit.WAN, 8),
            new Tile_1.default(Tile_1.Suit.WAN, 9),
            new Tile_1.default(Tile_1.Suit.WIND, 2),
            new Tile_1.default(Tile_1.Suit.WIND, 2),
            new Tile_1.default(Tile_1.Suit.WIND, 2),
        ];
        expect(Tile_1.default.winningHand(hand, 1, 4)).toBeTruthy();
    });
    test('No dragon runs', () => {
        const hand = [
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 1),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 3),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 4),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 5),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 6),
            new Tile_1.default(Tile_1.Suit.DRAGON, 7),
            new Tile_1.default(Tile_1.Suit.DRAGON, 8),
            new Tile_1.default(Tile_1.Suit.DRAGON, 9),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
            new Tile_1.default(Tile_1.Suit.BAMBOO, 2),
        ];
        expect(Tile_1.default.winningHand(hand, 1, 4)).toBeFalsy();
    });
});
//# sourceMappingURL=Tile.test.js.map