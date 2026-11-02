// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest';

const handlers: Record<string, (e: { detail: { page: unknown } }) => void> = {};
vi.mock('@inertiajs/react', () => ({
  router: {
    on: (name: string, fn: (e: { detail: { page: unknown } }) => void) => {
      handlers[name] = fn;
    },
  },
}));

describe('currentCsrfToken', () => {
  beforeEach(() => {
    vi.resetModules();
    document.body.innerHTML =
      '<script data-page="app" type="application/json">{"props":{"csrfToken":"tok"}}</script>';
  });

  it('reads the embedded page before any page event', async () => {
    const { currentCsrfToken } = await import('./csrf-token');
    expect(currentCsrfToken()).toBe('tok');
  });

  it('does not resurrect the embedded token after navigating to an anonymous page', async () => {
    const { currentCsrfToken } = await import('./csrf-token');
    expect(currentCsrfToken()).toBe('tok');
    handlers.navigate({ detail: { page: { props: {} } } });
    expect(currentCsrfToken()).toBeNull();
  });
});
