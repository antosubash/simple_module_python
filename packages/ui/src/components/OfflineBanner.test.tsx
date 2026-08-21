import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({
    t: (key: string) =>
      ({
        'host.offline.title': "You're offline",
        'host.offline.description': 'Changes may not be saved until your connection returns.',
        'host.offline.restored': 'Back online',
      })[key] ?? key,
  }),
  keys: {
    host: {
      offline: {
        title: 'host.offline.title',
        description: 'host.offline.description',
        restored: 'host.offline.restored',
      },
    },
  },
}));

import { OfflineBanner } from './OfflineBanner';

/** Drive connectivity the way the browser does: flip navigator.onLine, then
 *  fire the event the hook actually listens for. */
function setConnectivity(online: boolean): void {
  Object.defineProperty(navigator, 'onLine', { value: online, configurable: true });
  act(() => {
    window.dispatchEvent(new Event(online ? 'online' : 'offline'));
  });
}

describe('OfflineBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
  });

  test('renders nothing while the connection is healthy', () => {
    render(<OfflineBanner />);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByRole('status')).toBeNull();
  });

  test('interrupts with an alert when the connection drops', () => {
    render(<OfflineBanner />);
    setConnectivity(false);
    // `alert`, not `status`: going offline changes what the user can do right
    // now, so it should interrupt rather than wait to be read.
    expect(screen.getByRole('alert')).toHaveTextContent("You're offline");
  });

  test('confirms recovery instead of vanishing silently', () => {
    render(<OfflineBanner />);
    setConnectivity(false);
    setConnectivity(true);
    // The bar that just disappears leaves the user unsure whether to retry
    // what they were doing — this is the assertion QA could not make
    // reliably against a real browser clock.
    expect(screen.getByRole('status')).toHaveTextContent('Back online');
  });

  test('clears the confirmation after it has been seen', () => {
    render(<OfflineBanner />);
    setConnectivity(false);
    setConnectivity(true);
    expect(screen.getByRole('status')).toBeTruthy();

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  test('a second outage re-arms the confirmation', () => {
    render(<OfflineBanner />);
    setConnectivity(false);
    setConnectivity(true);
    act(() => {
      vi.advanceTimersByTime(3000);
    });

    setConnectivity(false);
    expect(screen.getByRole('alert')).toHaveTextContent("You're offline");
    setConnectivity(true);
    expect(screen.getByRole('status')).toHaveTextContent('Back online');
  });
});
