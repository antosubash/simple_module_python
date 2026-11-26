import { DESKTOP_SIDEBAR_QUERY, useDrawerA11y } from '@simple-module-py/ui/layouts/useDrawerA11y';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useCallback, useRef, useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type Listener = (e: MediaQueryListEvent) => void;

/** A controllable viewport for min-width queries: jsdom ships no matchMedia. */
function installMatchMedia(initialWidth = 40) {
  let width = initialWidth;
  const queries = new Map<string, { matches: boolean; listeners: Set<Listener> }>();
  window.matchMedia = vi.fn((query: string) => {
    const state = queries.get(query) ?? {
      matches: width >= Number.parseFloat(query.slice('(min-width: '.length)),
      listeners: new Set<Listener>(),
    };
    queries.set(query, state);
    return {
      get matches() {
        return state.matches;
      },
      media: query,
      addEventListener: (_: string, fn: Listener) => state.listeners.add(fn),
      removeEventListener: (_: string, fn: Listener) => state.listeners.delete(fn),
    } as unknown as MediaQueryList;
  });
  return {
    queries,
    resize(nextWidth: number) {
      width = nextWidth;
      for (const [query, state] of queries) {
        const matches = width >= Number.parseFloat(query.slice('(min-width: '.length));
        if (matches === state.matches) continue;
        state.matches = matches;
        for (const fn of [...state.listeners]) fn({ matches } as MediaQueryListEvent);
      }
    },
  };
}

function Drawer({ children, desktopQuery }: { children?: React.ReactNode; desktopQuery?: string }) {
  const [open, setOpen] = useState(true);
  const close = useCallback(() => setOpen(false), []);
  const ref = useRef<HTMLElement>(null);
  useDrawerA11y(open, close, ref, { desktopQuery });
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
    document.body.style.overflow = '';
    vi.restoreAllMocks();
  });

  it('closes, releasing the trap, when the viewport crosses to desktop', () => {
    const media = installMatchMedia();
    render(<Drawer />);
    const drawer = screen.getByTestId('drawer');
    expect(drawer.dataset.open).toBe('true');
    expect(media.queries.get(DESKTOP_SIDEBAR_QUERY)?.listeners.size).toBe(1);

    act(() => media.resize(64));

    expect(drawer.dataset.open).toBe('false');
    // Keep observing so a closed drawer becomes inert on a return to mobile.
    expect(media.queries.get(DESKTOP_SIDEBAR_QUERY)?.listeners.size).toBe(1);
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

  it.each([
    { desktopQuery: undefined, breakpoint: 64 },
    { desktopQuery: '(min-width: 48rem)', breakpoint: 48 },
  ])('uses $breakpoint rem for modal behaviour', ({ desktopQuery, breakpoint }) => {
    const media = installMatchMedia(breakpoint - 1);
    document.body.style.overflow = 'auto';
    render(<button type="button">opener</button>);
    const opener = screen.getByRole('button', { name: 'opener' });
    opener.focus();
    render(<Drawer desktopQuery={desktopQuery} />);
    const drawer = screen.getByTestId('drawer');
    const first = screen.getByRole('button', { name: 'first' });
    const last = screen.getByRole('button', { name: 'last' });
    expect(document.activeElement).toBe(first);
    expect(document.body.style.overflow).toBe('hidden');
    last.focus();
    fireEvent.keyDown(last, { key: 'Tab' });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(last);

    act(() => media.resize(breakpoint));

    expect(drawer.dataset.open).toBe('false');
    expect(drawer).not.toHaveAttribute('inert');
    expect(drawer).not.toHaveAttribute('aria-hidden');
    expect(document.body.style.overflow).toBe('auto');
    expect(document.activeElement).toBe(opener);
    last.focus();
    expect(fireEvent.keyDown(last, { key: 'Tab' })).toBe(true);
    expect(document.activeElement).toBe(last);
    expect(fireEvent.keyDown(last, { key: 'Escape' })).toBe(true);

    act(() => media.resize(breakpoint - 1));
    expect(drawer).toHaveAttribute('inert');
    expect(drawer).toHaveAttribute('aria-hidden', 'true');
  });

  it('does not trap focus or lock scrolling above a custom breakpoint on mount', () => {
    installMatchMedia(56);
    render(<button type="button">opener</button>);
    const opener = screen.getByRole('button', { name: 'opener' });
    opener.focus();
    render(<Drawer desktopQuery="(min-width: 48rem)" />);
    expect(screen.getByTestId('drawer').dataset.open).toBe('false');
    expect(document.activeElement).toBe(opener);
    expect(document.body.style.overflow).toBe('');
    expect(fireEvent.keyDown(opener, { key: 'Escape' })).toBe(true);
  });

  it('keeps focus and the original opener across equal inline options', () => {
    installMatchMedia();
    render(<button type="button">opener</button>);
    const opener = screen.getByRole('button', { name: 'opener' });
    opener.focus();
    const view = render(<Drawer desktopQuery="(min-width: 48rem)" />);
    const last = screen.getByRole('button', { name: 'last' });
    last.focus();
    view.rerender(<Drawer desktopQuery="(min-width: 48rem)" />);
    expect(document.activeElement).toBe(last);
    expect(window.matchMedia).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(last, { key: 'Escape' });
    expect(screen.getByTestId('drawer').dataset.open).toBe('false');
    expect(document.activeElement).toBe(opener);
    expect(document.body.style.overflow).toBe('');
  });

  it('switches to a changed query and removes the previous listener', () => {
    const media = installMatchMedia(56);
    const view = render(<Drawer />);
    expect(screen.getByTestId('drawer').dataset.open).toBe('true');
    view.rerender(<Drawer desktopQuery="(min-width: 48rem)" />);
    expect(screen.getByTestId('drawer').dataset.open).toBe('false');
    expect(document.body.style.overflow).toBe('');
    expect(media.queries.get(DESKTOP_SIDEBAR_QUERY)?.listeners.size).toBe(0);
    act(() => media.resize(40));
    expect(screen.getByTestId('drawer')).toHaveAttribute('inert');
    view.unmount();
    expect(media.queries.get('(min-width: 48rem)')?.listeners.size).toBe(0);
  });

  it.each(['', 'important'])(
    'preserves overflow priority "%s" while locking and restoring scrolling',
    (priority) => {
      installMatchMedia();
      document.body.style.setProperty('overflow', 'scroll', priority);
      const view = render(<Drawer desktopQuery="(min-width: 48rem)" />);
      expect(document.body.style.overflow).toBe('hidden');
      expect(document.body.style.getPropertyPriority('overflow')).toBe(priority);
      view.unmount();
      expect(document.body.style.overflow).toBe('scroll');
      expect(document.body.style.getPropertyPriority('overflow')).toBe(priority);
    },
  );
});
