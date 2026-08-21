import { router } from '@inertiajs/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { shouldInterceptNavigation, startSpaLinkInterception } from './spa-links';

/**
 * The rule has to be conservative in both directions. Taking over a link
 * Inertia cannot render replaces a working download with an error modal;
 * leaving an ordinary page link alone puts back the full document reload —
 * and with it the blank frame a client-rendered app paints while it boots.
 *
 * The cases pinned here are the ones a naive "same origin?" test gets wrong.
 */

const HERE = new URL('http://localhost:3000/p/who-we-are');

function anchor(html: string): HTMLAnchorElement {
  document.body.innerHTML = html;
  const el = document.body.querySelector('a');
  if (!el) throw new Error(`no anchor in ${html}`);
  return el;
}

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('shouldInterceptNavigation', () => {
  it('takes over an ordinary same-origin page link', () => {
    expect(shouldInterceptNavigation(anchor('<a href="/p/outputs">Outputs</a>'), HERE)).toBe(true);
    expect(shouldInterceptNavigation(anchor('<a href="/">Home</a>'), HERE)).toBe(true);
    expect(
      shouldInterceptNavigation(anchor('<a href="http://localhost:3000/p/faqs">FAQs</a>'), HERE),
    ).toBe(true);
  });

  it('leaves other origins to the browser', () => {
    expect(
      shouldInterceptNavigation(anchor('<a href="https://example.org/x">Away</a>'), HERE),
    ).toBe(false);
  });

  it('leaves non-http schemes alone', () => {
    expect(shouldInterceptNavigation(anchor('<a href="mailto:a@b.org">Mail</a>'), HERE)).toBe(
      false,
    );
    expect(shouldInterceptNavigation(anchor('<a href="tel:+4312345">Call</a>'), HERE)).toBe(false);
  });

  it('leaves anything that looks like a file to the browser', () => {
    // Editor-uploaded documents are served from the same origin; routing one
    // through Inertia swaps the download for its error modal.
    for (const href of ['/media/report.pdf', '/uploads/logo.png', '/static/dist/main.js']) {
      expect(shouldInterceptNavigation(anchor(`<a href="${href}">f</a>`), HERE)).toBe(false);
    }
  });

  it('respects an explicit opt-out', () => {
    expect(shouldInterceptNavigation(anchor('<a href="/p/x" download>Save</a>'), HERE)).toBe(false);
    expect(shouldInterceptNavigation(anchor('<a href="/p/x" target="_blank">New</a>'), HERE)).toBe(
      false,
    );
    expect(shouldInterceptNavigation(anchor('<a href="/p/x" rel="external">Out</a>'), HERE)).toBe(
      false,
    );
    expect(shouldInterceptNavigation(anchor('<a href="/p/x" data-native-link>P</a>'), HERE)).toBe(
      false,
    );
  });

  it('keeps target="_self" — it means this frame, which is what we do', () => {
    expect(shouldInterceptNavigation(anchor('<a href="/p/x" target="_self">Here</a>'), HERE)).toBe(
      true,
    );
  });

  it('leaves in-page anchors to the browser', () => {
    // Including `href="#"`, which is what a pagebuilder nav row holds before an
    // editor fills it in — taking it over would re-fetch the current page.
    for (const href of ['#', '#section', '/p/who-we-are', '/p/who-we-are#team']) {
      expect(shouldInterceptNavigation(anchor(`<a href="${href}">a</a>`), HERE)).toBe(false);
    }
  });

  it('does not touch anchors inside a Puck editor surface', () => {
    // An editor rendering with `iframe={{ enabled: false }}` puts the edited
    // page's real nav anchors into the admin document.
    for (const wrapper of ['data-puck-preview', 'data-puck-component']) {
      const el = anchor(`<div ${wrapper}><a href="/p/outputs">Outputs</a></div>`);
      expect(shouldInterceptNavigation(el, HERE)).toBe(false);
    }
  });

  it('ignores an anchor with no href', () => {
    document.body.innerHTML = '<a>no href</a>';
    const el = document.body.querySelector('a') as HTMLAnchorElement;
    expect(shouldInterceptNavigation(el, HERE)).toBe(false);
  });
});

describe('startSpaLinkInterception', () => {
  let stop: () => void;
  let visit: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.history.pushState({}, '', '/p/who-we-are');
    visit = vi.spyOn(router, 'visit').mockImplementation(() => undefined);
    stop = startSpaLinkInterception();
  });

  afterEach(() => {
    stop();
    visit.mockRestore();
  });

  /**
   * Dispatch a click and report whether the handler under test took it over.
   *
   * The verdict is read on `window` — the last stop in the bubble path, after
   * the document listener — and the event is then cancelled unconditionally.
   * Without that, every click this code correctly declines would reach jsdom's
   * link activation, which floods the run with "Not implemented: navigation"
   * and would drown a real error.
   */
  function click(el: Element, init: MouseEventInit = {}): { prevented: boolean } {
    let prevented = false;
    const guard = (event: Event): void => {
      prevented = event.defaultPrevented;
      event.preventDefault();
    };
    window.addEventListener('click', guard);
    el.dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init }),
    );
    window.removeEventListener('click', guard);
    return { prevented };
  }

  it('visits an internal link instead of letting the browser navigate', () => {
    expect(click(anchor('<a href="/p/outputs">Outputs</a>')).prevented).toBe(true);
    expect(visit).toHaveBeenCalledWith('http://localhost:3000/p/outputs');
  });

  it('follows a click on an element nested inside the link', () => {
    // Authored links wrap icons and spans; the click target is not the anchor.
    document.body.innerHTML = '<a href="/p/outputs"><span id="inner">Go</span></a>';
    click(document.getElementById('inner') as Element);
    expect(visit).toHaveBeenCalledWith('http://localhost:3000/p/outputs');
  });

  it('leaves a click another handler already took', () => {
    // This is what keeps an Inertia <Link> from being visited twice: its own
    // onClick preventDefaults before the event reaches the document.
    const el = anchor('<a href="/p/outputs">Outputs</a>');
    el.addEventListener('click', (e) => e.preventDefault());
    click(el);
    expect(visit).not.toHaveBeenCalled();
  });

  it('leaves modified and non-left clicks to the browser', () => {
    const el = anchor('<a href="/p/outputs">Outputs</a>');
    for (const init of [
      { metaKey: true },
      { ctrlKey: true },
      { shiftKey: true },
      { altKey: true },
      { button: 1 },
    ]) {
      expect(click(el, init).prevented).toBe(false);
    }
    expect(visit).not.toHaveBeenCalled();
  });

  it('leaves a link it should not take over', () => {
    expect(click(anchor('<a href="/media/report.pdf">Report</a>')).prevented).toBe(false);
    expect(visit).not.toHaveBeenCalled();
  });

  it('stops intercepting once torn down', () => {
    stop();
    expect(click(anchor('<a href="/p/outputs">Outputs</a>')).prevented).toBe(false);
    expect(visit).not.toHaveBeenCalled();
    stop = () => undefined; // afterEach must not tear down twice
  });
});
