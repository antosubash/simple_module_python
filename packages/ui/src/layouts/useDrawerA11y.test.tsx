import { act, fireEvent, render, screen } from '@testing-library/react';
import { useCallback, useRef, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DESKTOP_SIDEBAR_QUERY, useDrawerA11y } from './useDrawerA11y';

type Listener = (e: MediaQueryListEvent) => void;

/** A controllable `matchMedia` for the desktop query: jsdom ships none. */
function installMatchMedia() {
  const listeners = new Set<Listener>();
  const mql = {
    matches: false,
    media: DESKTOP_SIDEBAR_QUERY,
    addEventListener: (_: string, fn: Listener) => listeners.add(fn),
    removeEventListener: (_: string, fn: Listener) => listeners.delete(fn),
  };
  window.matchMedia = vi.fn(() => mql as unknown as MediaQueryList);
  return {
    listeners,
    toDesktop() {
      mql.matches = true;
      for (const fn of [...listeners]) fn({ matches: true } as MediaQueryListEvent);
    },
  };
}

function Drawer({ children }: { children?: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  const close = useCallback(() => setOpen(false), []);
  const ref = useRef<HTMLElement>(null);
  useDrawerA11y(open, close, ref);
  return (
    <aside ref={ref} data-testid="drawer" data-open={open}>
      {children ?? (
        <>
          <button type="button">first</button>
          <button type="button">last</button>
        </>
      )}
    </aside>
  );
}

describe('useDrawerA11y', () => {
  const realMatchMedia = window.matchMedia;

  beforeEach(() => {
    // jsdom lays nothing out; an element styled `display: none` stands in for
    // one hidden by CSS (a `lg:hidden` control).
    vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(function (
      this: HTMLElement,
    ) {
      return (this.style.display === 'none' ? [] : [{}]) as unknown as DOMRectList;
    });
  });

  afterEach(() => {
    window.matchMedia = realMatchMedia;
    vi.restoreAllMocks();
  });

  it('closes, releasing the trap, when the viewport crosses to desktop', () => {
    const media = installMatchMedia();
    render(<Drawer />);
    const drawer = screen.getByTestId('drawer');
    expect(drawer.dataset.open).toBe('true');
    expect(media.listeners.size).toBe(1);

    act(() => media.toDesktop());

    expect(drawer.dataset.open).toBe('false');
    expect(media.listeners.size).toBe(0);
    const last = screen.getByRole('button', { name: 'last' });
    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(document.activeElement).toBe(last);
  });

  it('skips focusable elements that are not rendered', () => {
    installMatchMedia();
    render(
      <Drawer>
        <button type="button" style={{ display: 'none' }}>
          css-hidden
        </button>
        <button type="button">visible</button>
        <div hidden>
          <button type="button">attr-hidden</button>
        </div>
        <div inert>
          <button type="button">inert</button>
        </div>
      </Drawer>,
    );
    const visible = screen.getByRole('button', { name: 'visible' });
    expect(document.activeElement).toBe(visible);
    fireEvent.keyDown(visible, { key: 'Tab' });
    expect(document.activeElement).toBe(visible);
    fireEvent.keyDown(visible, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(visible);
  });
});
