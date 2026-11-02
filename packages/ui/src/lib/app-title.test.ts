import { afterEach, describe, expect, test } from 'vitest';
import { formatTitle, setTitleAppName } from './app-title';

// The app name is module-level state — reset it after each test.
afterEach(() => setTitleAppName(null));

describe('formatTitle', () => {
  test('defaults to the framework name', () => {
    expect(formatTitle('Dashboard')).toBe('Dashboard — SimpleModule');
    expect(formatTitle()).toBe('SimpleModule');
    expect(formatTitle('')).toBe('SimpleModule');
  });

  test('uses the configured app name once set', () => {
    setTitleAppName('Acme');
    expect(formatTitle('Dashboard')).toBe('Dashboard — Acme');
    expect(formatTitle()).toBe('Acme');
  });

  test('trims and falls back on blank/null names', () => {
    setTitleAppName('  Acme  ');
    expect(formatTitle('X')).toBe('X — Acme');
    setTitleAppName('   ');
    expect(formatTitle('X')).toBe('X — SimpleModule');
    setTitleAppName('Acme');
    setTitleAppName(null);
    expect(formatTitle('X')).toBe('X — SimpleModule');
  });
});
