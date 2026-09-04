import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  applyTheme,
  initTheme,
  readThemePreference,
  resolveTheme,
  setThemePreference,
  THEME_STORAGE_KEY,
} from './theme';

/** Stand in for matchMedia so a test can say what the OS prefers. */
function stubPrefersDark(prefersDark: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql = {
    matches: prefersDark,
    addEventListener: (_: string, fn: (e: MediaQueryListEvent) => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: (e: MediaQueryListEvent) => void) => listeners.delete(fn),
  };
  vi.stubGlobal(
    'matchMedia',
    vi.fn(() => mql),
  );
  return { listeners, mql };
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove('dark');
  vi.unstubAllGlobals();
});

describe('resolveTheme', () => {
  it('follows the OS only when the preference is "system"', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
  });
});

describe('readThemePreference', () => {
  it('defaults to "system" when nothing is stored', () => {
    expect(readThemePreference()).toBe('system');
  });

  it('reads a stored preference back', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(readThemePreference()).toBe('dark');
  });

  it('ignores a stored value that is not a preference', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'neon');
    expect(readThemePreference()).toBe('system');
  });
});

describe('applyTheme', () => {
  it('adds the dark class for "dark" and removes it for "light"', () => {
    stubPrefersDark(false);
    applyTheme('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    applyTheme('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('asks the OS when the preference is "system"', () => {
    stubPrefersDark(true);
    applyTheme('system');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });
});

describe('setThemePreference', () => {
  it('persists and applies in one step', () => {
    stubPrefersDark(false);
    setThemePreference('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });
});

describe('initTheme', () => {
  it('applies the stored preference straight away', () => {
    stubPrefersDark(false);
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    const stop = initTheme();
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    stop();
  });

  it('follows later OS changes while the preference is "system"', () => {
    const { listeners, mql } = stubPrefersDark(false);
    const stop = initTheme();
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    mql.matches = true;
    for (const fn of listeners) fn({ matches: true } as MediaQueryListEvent);
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    stop();
    expect(listeners.size).toBe(0);
  });

  it('stops following the OS once an explicit preference is stored', () => {
    const { listeners, mql } = stubPrefersDark(false);
    localStorage.setItem(THEME_STORAGE_KEY, 'light');
    const stop = initTheme();

    mql.matches = true;
    for (const fn of listeners) fn({ matches: true } as MediaQueryListEvent);
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    stop();
  });
});
