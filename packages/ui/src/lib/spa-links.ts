import { router } from '@inertiajs/react';

/**
 * Route in-app link clicks through Inertia instead of the browser.
 *
 * A simple_module app is client-rendered: the root template ships
 * `<div id="app"></div>` empty and `app.tsx` fills it with
 * `createRoot().render()`. So a navigation that creates a *new document* paints
 * an empty white body first, and only fills in once the bundle has run — one
 * blank frame on a fast connection, and the whole boot time on a slow one.
 *
 * Admin screens never hit this, because the shell navigates with Inertia's
 * `<Link>`. Authored content is the problem: pagebuilder widgets, and the
 * markdown/rich-text fields inside them, render author-entered URLs as plain
 * `<a href>`. There is no component to swap for a `<Link>` — the anchors come
 * out of a markdown parser — so a public site reloaded the whole document on
 * every click of its own nav.
 *
 * Delegating on the document catches all of them at once, whatever produced
 * the anchor. Call `startSpaLinkInterception()` once, from `app.tsx`, before
 * the first render.
 *
 * It is opt-in rather than an import side effect: installing a global click
 * listener is not something a UI package should do just by being imported.
 */

/** A trailing `.ext` on the last path segment — `/media/report.pdf`. */
const LOOKS_LIKE_A_FILE = /\.[a-z0-9]+$/i;

/**
 * Marks a subtree whose anchors must keep the browser's own behaviour.
 *
 * Puck sets these on its editor surfaces. An editor that renders with
 * `iframe={{ enabled: false }}` — pagebuilder's site-layout editor does —
 * puts the real nav anchors of the page being edited into the admin document,
 * where taking them over would be wrong.
 */
const EDITOR_SURFACE = '[data-puck-preview],[data-puck-component]';

/**
 * Whether the SPA should take over this anchor, given the page it is on.
 *
 * `here` is a parameter rather than a read of `window.location` so the decision
 * is a pure function of its inputs, and so the base for resolving the href is
 * explicit — `anchor.href` would quietly resolve against the document's base
 * URL instead.
 *
 * The bias is towards leaving links alone. Taking over a URL Inertia cannot
 * render turns a working download into an error modal, while missing one only
 * costs the reload this is trying to avoid.
 */
export function shouldInterceptNavigation(anchor: HTMLAnchorElement, here: URL): boolean {
  const href = anchor.getAttribute('href');
  if (!href) return false;

  // Author opt-outs, plus the two the HTML spec already provides.
  if (anchor.hasAttribute('download')) return false;
  if (anchor.hasAttribute('data-native-link')) return false;
  const target = anchor.getAttribute('target');
  if (target && target !== '_self') return false;
  if ((anchor.getAttribute('rel') ?? '').split(/\s+/).includes('external')) return false;

  if (anchor.closest(EDITOR_SURFACE)) return false;

  let url: URL;
  try {
    url = new URL(href, here.href);
  } catch {
    return false;
  }

  // `mailto:`, `tel:`, and anything else the browser owns outright.
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return false;
  if (url.origin !== here.origin) return false;

  // Same document: `#`, `#section`, or a link back to the current page. The
  // browser handles all three correctly, and `href="#"` is what a pagebuilder
  // nav row holds before an editor fills it in.
  if (url.pathname === here.pathname && url.search === here.search) return false;

  // Same origin but not a page: media uploads, module static mounts. Inertia
  // would request these expecting a page payload and raise its error modal
  // over the file. `startSpaLinkInterception` keeps a hard-navigation fallback
  // for whatever still gets through.
  if (LOOKS_LIKE_A_FILE.test(url.pathname.split('/').pop() ?? '')) return false;

  return true;
}

/** A click the browser would otherwise handle by navigating this frame. */
function isPlainLeftClick(event: MouseEvent): boolean {
  return (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey &&
    !event.defaultPrevented
  );
}

/**
 * Install the delegated click handler. Call once, from `app.tsx`.
 *
 * Returns a function that removes it again, which is what tests use; an app has
 * no reason to.
 */
export function startSpaLinkInterception(): () => void {
  // Set when a click is taken over, cleared when the visit comes back as a real
  // Inertia response. If it does not, the URL was not a page after all and the
  // browser should have had it — hand it back rather than showing Inertia's
  // error modal over a link that used to work.
  let takenOver: string | null = null;

  const offSuccess = router.on('success', () => {
    takenOver = null;
  });

  const offInvalid = router.on('invalid', (event) => {
    if (!takenOver) return;
    const url = takenOver;
    takenOver = null;
    event.preventDefault();
    window.location.href = url;
  });

  // Bubble phase on the document, so React's own handlers have already run —
  // they are attached at the root container, inside this. An Inertia `<Link>`
  // therefore shows up here as `defaultPrevented`, and is left alone instead of
  // being visited a second time.
  const onClick = (event: MouseEvent): void => {
    if (!isPlainLeftClick(event)) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    const anchor = target.closest('a[href]');
    if (!(anchor instanceof HTMLAnchorElement)) return;

    const here = new URL(window.location.href);
    if (!shouldInterceptNavigation(anchor, here)) return;

    const url = new URL(anchor.getAttribute('href') as string, here.href).href;
    event.preventDefault();
    takenOver = url;
    router.visit(url);
  };

  document.addEventListener('click', onClick);

  return () => {
    document.removeEventListener('click', onClick);
    offSuccess();
    offInvalid();
  };
}
