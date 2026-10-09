import { describe, expect, test } from 'vitest';
import { BASE_PRIMARY_RAMP, contrastRatio, deriveBrandRamp, hexToOklch } from './color';

describe('hexToOklch', () => {
  test('white is light and (near) achromatic', () => {
    const c = hexToOklch('#ffffff');
    expect(c).not.toBeNull();
    expect(c?.l).toBeGreaterThan(0.99);
    expect(c?.c).toBeLessThan(0.01);
  });

  test('black is dark', () => {
    expect(hexToOklch('#000000')?.l).toBeLessThan(0.01);
  });

  test('red sits in the expected OKLCH hue band (~29°)', () => {
    const c = hexToOklch('#ff0000');
    expect(c?.h).toBeGreaterThan(20);
    expect(c?.h).toBeLessThan(40);
  });

  test('3-digit and 6-digit hex agree', () => {
    expect(hexToOklch('#f00')?.h).toBeCloseTo(hexToOklch('#ff0000')?.h ?? -1, 1);
  });

  test('returns null for malformed input', () => {
    expect(hexToOklch('red')).toBeNull();
    expect(hexToOklch('#12')).toBeNull();
    expect(hexToOklch('')).toBeNull();
  });
});

describe('deriveBrandRamp', () => {
  test('emits every ramp step plus the base tokens', () => {
    const ramp = deriveBrandRamp('#1a7dd1');
    expect(ramp).not.toBeNull();
    for (const { step } of BASE_PRIMARY_RAMP) {
      expect(ramp?.[`--color-primary-${step}`]).toMatch(/^oklch\(/);
    }
    // Base tokens are the exact picked colour.
    expect(ramp?.['--primary']).toBe('#1a7dd1');
    expect(ramp?.['--sidebar-primary']).toBe('#1a7dd1');
  });

  test('a near-grey brand yields a near-grey ramp (low chroma)', () => {
    const ramp = deriveBrandRamp('#808080');
    const step600 = ramp?.['--color-primary-600'] ?? '';
    const chroma = Number.parseFloat(step600.split(' ')[1]);
    expect(chroma).toBeLessThan(0.02);
  });

  test('a vivid brand keeps meaningful chroma', () => {
    const ramp = deriveBrandRamp('#ff0000');
    const step600 = ramp?.['--color-primary-600'] ?? '';
    const chroma = Number.parseFloat(step600.split(' ')[1]);
    expect(chroma).toBeGreaterThan(0.1);
  });

  test('returns null for malformed input', () => {
    expect(deriveBrandRamp('not-a-color')).toBeNull();
  });
});

const DARK_INK = 'oklch(0.2 0.02 250)';
const WHITE = 'oklch(1 0 0)';

describe('brand foreground ink (#420)', () => {
  test.each([
    ['#62B8E2', DARK_INK],
    ['#9AD3EF', DARK_INK],
    ['#2E6DB0', WHITE],
    ['#16276E', WHITE],
  ])('%s gets %s', (hex, ink) => {
    const ramp = deriveBrandRamp(hex);
    expect(ramp?.['--primary-foreground']).toBe(ink);
    expect(ramp?.['--sidebar-primary-foreground']).toBe(ink);
  });

  test('white is rejected on light brands because it fails WCAG AA', () => {
    expect(contrastRatio('#62B8E2', '#ffffff')).toBeLessThan(4.5);
  });

  test('contrastRatio is 21 for black on white and 1 for unparseable input', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5);
    expect(contrastRatio('nope', '#ffffff')).toBe(1);
  });
});
