/**
 * Light/dark preference, stored and applied.
 *
 * Tailwind's dark variant keys off a `dark` class on `<html>`, so the whole
 * feature is one class plus somewhere to remember the choice. "system" is the
 * default and stays live: a laptop that flips to dark at sunset should take
 * the app with it, which is why `initTheme` subscribes rather than reading the
 * media query once at boot.
 */

export type ThemePreference = 'light' | 'dark' | 'system';

export const THEME_STORAGE_KEY = 'sm.theme';

const DARK_QUERY = '(prefers-color-scheme: dark)';

function isPreference(value: unknown): value is ThemePreference {
  return value === 'light' || value === 'dark' || value === 'system';
}

/** What the OS currently asks for; false anywhere `matchMedia` is unavailable. */
function prefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(DARK_QUERY).matches;
}

export function readThemePreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system';
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(stored) ? stored : 'system';
  } catch {
    // Storage is denied in private-mode Safari and in sandboxed iframes.
    // Following the OS is a better answer there than throwing.
    return 'system';
  }
}

export function resolveTheme(pref: ThemePreference, prefersDarkNow: boolean): 'light' | 'dark' {
  if (pref === 'system') return prefersDarkNow ? 'dark' : 'light';
  return pref;
}

export function applyTheme(pref: ThemePreference): void {
  if (typeof document === 'undefined') return;
  const resolved = resolveTheme(pref, prefersDark());
  document.documentElement.classList.toggle('dark', resolved === 'dark');
}

export function setThemePreference(pref: ThemePreference): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    // Same as reading: an un-persisted choice still applies for this session.
  }
  applyTheme(pref);
}

/**
 * Apply the stored preference and keep following the OS while it is "system".
 * Returns the unsubscribe so a caller mounting this in an effect can clean up.
 */
export function initTheme(): () => void {
  applyTheme(readThemePreference());
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {};
  }
  const media = window.matchMedia(DARK_QUERY);
  // Re-read the preference rather than closing over it: an explicit choice
  // made after boot must stop the OS from overriding it.
  const onChange = () => applyTheme(readThemePreference());
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}
