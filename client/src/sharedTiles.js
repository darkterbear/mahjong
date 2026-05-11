// client/src/sharedTiles.js
// Map subterfuge tile IDs (0..41) to image URLs and human labels.

const SUITS = {
  bamboo: 's',
  wan: 'w',
  dots: 't',
  wind: 'f',
  dragon: 'd',
  flower: 'h',
};

const TILE_BASE = 'https://files.terranceli.com/mahjong';

export function tileImageUrl(tileId) {
  if (tileId < 0 || tileId > 41) return `${TILE_BASE}/MJhide.svg`;
  if (tileId < 9)  return `${TILE_BASE}/MJ${SUITS.bamboo}${tileId + 1}-.svg`;
  if (tileId < 18) return `${TILE_BASE}/MJ${SUITS.wan}${tileId - 8}-.svg`;
  if (tileId < 27) return `${TILE_BASE}/MJ${SUITS.dots}${tileId - 17}-.svg`;
  if (tileId < 31) return `${TILE_BASE}/MJ${SUITS.wind}${tileId - 26}-.svg`;
  if (tileId < 34) return `${TILE_BASE}/MJ${SUITS.dragon}${tileId - 30}-.svg`;
  return `${TILE_BASE}/MJ${SUITS.flower}${tileId - 33}-.svg`;
}

export function hiddenTileUrl() {
  return `${TILE_BASE}/MJhide.svg`;
}

export function tileLabel(tileId) {
  if (tileId < 9)  return `${tileId + 1} Bamboo`;
  if (tileId < 18) return `${tileId - 8} Characters`;
  if (tileId < 27) return `${tileId - 17} Dots`;
  if (tileId < 31) return ['East','South','West','North'][tileId - 27] + ' Wind';
  if (tileId < 34) return ['Red','Green','White'][tileId - 31] + ' Dragon';
  return `Flower ${tileId - 33}`;
}

export function isFlower(tileId) {
  return tileId >= 34 && tileId < 42;
}
