import { http } from '@inertiajs/core';
import { router } from '@inertiajs/react';
import { afterEach, expect, it, vi } from 'vitest';
import { startSpaLinkInterception } from './spa-links';

let stop: (() => void) | undefined;
let removeHttpExceptionListener: (() => void) | undefined;

afterEach(() => {
  stop?.();
  removeHttpExceptionListener?.();
  router.cancelAll();
  router.flushAll();
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('hard-navigates when a plain link consumes prefetched non-Inertia HTML', async () => {
  window.history.replaceState({}, '', '/p/who-we-are');
  // jsdom cannot navigate documents; retain URL semantics while observing the href assignment.
  const location = new URL(window.location.href);
  vi.stubGlobal('location', location);
  const initialNavigation = new Promise<void>((resolve) =>
    router.once('navigate', () => resolve()),
  );
  router.init({
    initialPage: {
      component: 'Home',
      props: { errors: {} },
      url: '/p/who-we-are',
      version: null,
      flash: {},
      rescuedProps: [],
    },
    resolveComponent: () => ({}),
    swapComponent: async () => {},
  });
  await initialNavigation;

  const request = vi.spyOn(http.getClient(), 'request').mockResolvedValue({
    status: 200,
    data: '<!doctype html><html><body>Legacy page</body></html>',
    headers: { 'content-type': 'text/html' },
  });
  const httpException = vi.fn(() => false);
  // Prevent the modal on regression so the failure reports the missing navigation cleanly.
  removeHttpExceptionListener = router.on('httpException', httpException);

  router.prefetch('/legacy-page?view=full#details');
  await vi.waitFor(() => {
    expect(router.getCached('/legacy-page?view=full#details')).toMatchObject({ inFlight: false });
  });
  expect(location.href).toBe('http://localhost:3000/p/who-we-are');
  expect(httpException).not.toHaveBeenCalled();

  stop = startSpaLinkInterception();
  const link = document.createElement('a');
  link.href = '/legacy-page?view=full#details';
  document.body.append(link);
  const click = new MouseEvent('click', { bubbles: true, cancelable: true });
  link.dispatchEvent(click);

  expect(click.defaultPrevented).toBe(true);
  await vi.waitFor(() => {
    expect(location.href).toBe('http://localhost:3000/legacy-page?view=full#details');
  });
  // The click must consume the cached HTML rather than making a second HTTP request.
  expect(request).toHaveBeenCalledTimes(1);
  expect(httpException).not.toHaveBeenCalled();
});
