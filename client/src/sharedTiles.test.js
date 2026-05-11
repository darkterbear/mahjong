import { tileImageUrl, tileLabel, isFlower } from './sharedTiles';

test('bamboo url', () => {
  expect(tileImageUrl(0)).toContain('MJs1-.svg');
  expect(tileImageUrl(8)).toContain('MJs9-.svg');
});

test('flower url', () => {
  expect(tileImageUrl(34)).toContain('MJh1-.svg');
});

test('label', () => {
  expect(tileLabel(0)).toBe('1 Bamboo');
  expect(tileLabel(31)).toBe('Red Dragon');
  expect(tileLabel(34)).toBe('Flower 1');
});

test('isFlower', () => {
  expect(isFlower(33)).toBe(false);
  expect(isFlower(34)).toBe(true);
  expect(isFlower(41)).toBe(true);
  expect(isFlower(42)).toBe(false);
});
