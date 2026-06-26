import { describe, expect, test } from 'vitest';
import { BASE_PRIMARY_RAMP, deriveBrandRamp, hexToOklch } from './color';

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
