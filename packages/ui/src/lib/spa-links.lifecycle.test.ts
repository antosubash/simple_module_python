import { router } from '@inertiajs/react';
import { afterEach, expect, it, vi } from 'vitest';
import { isExcluded, startSpaLinkInterception } from './spa-links';

type VisitCallbacks = {
  onSuccess?: () => void;
  onFinish?: () => void;
  onCancel?: () => void;
  onError?: () => void;
  onHttpException?: () => boolean | undefined;
};

afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function stubLocation() {
  const location = { href: 'http://localhost:3000/p/who-we-are' };
  vi.stubGlobal('location', location);
  return location;
}

it.each(['/api', '/api/'])('matches path segments for %s', (prefix) => {
  for (const path of ['/api', '/api/', '/api/users']) {
    expect(isExcluded(new URL(path, window.location.href), prefix)).toBe(true);
  }
  expect(isExcluded(new URL('/api-docs', window.location.href), prefix)).toBe(false);
  expect(isExcluded(new URL('/any', window.location.href), '/')).toBe(true);
});

it.each(['onSuccess', 'onCancel', 'onError'] as const)(
  'clears fallback state on per-visit %s',
  (callback) => {
    const location = stubLocation();
    let recorded: VisitCallbacks | undefined;
    vi.spyOn(router, 'visit').mockImplementation((_url, options) => {
      recorded = options as VisitCallbacks;
    });
    const stop = startSpaLinkInterception();
    const link = document.createElement('a');
    link.href = '/some-page';
    document.body.append(link);
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    recorded?.[callback]?.();
    expect(recorded?.onHttpException?.()).toBeUndefined();
    expect(location.href).toBe('http://localhost:3000/p/who-we-are');
    stop();
  },
);

it('keeps the second visit fallback when interrupting an in-flight request', () => {
  const location = stubLocation();
  const visits: VisitCallbacks[] = [];
  vi.spyOn(router, 'visit').mockImplementation((_url, options) => {
    const current = options as VisitCallbacks;
    const previous = visits.at(-1);
    visits.push(current);
    // Inertia interrupts the active synchronous request and fires cancel + finish synchronously.
    previous?.onCancel?.();
    previous?.onFinish?.();
  });

  const stop = startSpaLinkInterception();
  const first = document.createElement('a');
  first.href = '/first';
  const second = document.createElement('a');
  second.href = '/second-html';
  document.body.append(first, second);

  first.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  second.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

  // Stale first-visit callback is ignored; active second visit falls back to hard navigation.
  expect(visits[0].onHttpException?.()).toBeUndefined();
  expect(visits[1].onHttpException?.()).toBe(false);
  expect(location.href).toBe('http://localhost:3000/second-html');
  stop();
});

it('suppresses in-flight callbacks and removes its click listener on teardown', () => {
  const location = stubLocation();
  let recorded: VisitCallbacks | undefined;
  vi.spyOn(router, 'visit').mockImplementation((_url, options) => {
    recorded = options as VisitCallbacks;
  });
  const remove = vi.spyOn(document, 'removeEventListener');
  const stop = startSpaLinkInterception();
  const link = document.createElement('a');
  link.href = '/pending';
  document.body.append(link);
  link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

  stop();
  expect(remove).toHaveBeenCalledWith('click', expect.any(Function));
  expect(recorded?.onHttpException?.()).toBeUndefined();
  expect(location.href).toBe('http://localhost:3000/p/who-we-are');
});
