import { describe, expect, test } from 'vitest';

import { describeTypes, formatBytes } from '../file_storage/pages/format';

describe('formatBytes', () => {
  test.each([
    [0, '0 B'],
    [512, '512 B'],
    [18 * 1024, '18 KB'],
    [840 * 1024, '840 KB'],
    [25 * 1024 * 1024, '25 MB'],
    [100 * 1024 * 1024, '100 MB'],
  ])('spends no characters on a precision it does not need: %i', (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });

  test('keeps one decimal where the value earns it', () => {
    expect(formatBytes(Math.round(1.2 * 1024 ** 3))).toBe('1.2 GB');
    expect(formatBytes(Math.round(1.25 * 1024 * 1024))).toBe('1.3 MB');
  });

  test('switches unit exactly at the boundary, never reading "1024 KB"', () => {
    expect(formatBytes(1023)).toBe('1023 B');
    expect(formatBytes(1024)).toBe('1 KB');
    expect(formatBytes(1024 * 1024 - 1)).toBe('1024 KB');
    expect(formatBytes(1024 * 1024)).toBe('1 MB');
  });
});

describe('describeTypes', () => {
  test('names the allow-list the way a person would say it', () => {
    expect(describeTypes(['application/pdf', 'image/png', 'text/csv', 'application/sql'])).toBe(
      'pdf, png, csv, sql',
    );
  });

  test('says each subtype once, however many families carry it', () => {
    expect(describeTypes(['image/png', 'application/png'])).toBe('png');
  });

  test('has nothing to say about an empty allow-list', () => {
    // The caller renders "any type" for `null`; `[]` means the opposite —
    // nothing passes — so inventing "any type" here would be a lie.
    expect(describeTypes([])).toBe('');
  });
});
