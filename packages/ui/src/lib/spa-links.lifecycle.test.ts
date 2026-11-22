import { router } from '@inertiajs/react';
import { afterEach, expect, it, vi } from 'vitest';
import { isExcluded, startSpaLinkInterception } from './spa-links';

afterEach(() => vi.restoreAllMocks());

it.each(['/api', '/api/'])('matches path segments for %s', (prefix) => {
  for (const path of ['/api', '/api/', '/api/users']) {
    expect(isExcluded(new URL(path, window.location.href), prefix)).toBe(true);
  }
  expect(isExcluded(new URL('/api-docs', window.location.href), prefix)).toBe(false);
  expect(isExcluded(new URL('/any', window.location.href), '/')).toBe(true);
});

it.each(['success', 'finish', 'cancel', 'error'])('clears fallback state on %s', (name) => {
  vi.spyOn(router, 'visit').mockImplementation(() => undefined);
  const stop = startSpaLinkInterception();
  const link = document.createElement('a');
  link.href = '/some-page';
  document.body.append(link);
  link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  document.dispatchEvent(new CustomEvent(`inertia:${name}`));
  const invalid = new CustomEvent('inertia:httpException', { cancelable: true });
  document.dispatchEvent(invalid);
  expect(invalid.defaultPrevented).toBe(false);
  stop();
  link.remove();
});

it('removes its lifecycle listeners on teardown', () => {
  const stop = startSpaLinkInterception();
  const remove = vi.spyOn(document, 'removeEventListener');
  stop();
  for (const name of ['success', 'finish', 'cancel', 'error', 'httpException']) {
    expect(remove).toHaveBeenCalledWith(`inertia:${name}`, expect.any(Function));
  }
});
