import { usePage } from '@inertiajs/react';
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

/**
 * Lets the app shell name the page currently rendered inside it.
 *
 * The breadcrumb lives in the topbar, which the layout owns, but the only
 * component that knows what the page is called is the page's own `PageShell`
 * — several levels below. Rather than restate every title in a route table
 * (which then drifts from the heading on screen), `PageShell` reports the one
 * it is already rendering and the shell reads it back.
 *
 * The phone bar needs more than a name: it carries the title, an optional back
 * chevron and one compact action, none of which the layout can know. They ride
 * along on the same report for the same reason.
 *
 * The report carries the url it was made from, so a heading is only ever used
 * for the page it came from: during an Inertia swap the layout re-renders with
 * the new url before the incoming page's effect runs, and a bare string would
 * show the previous page's title against the new section for a frame.
 */

/** The phone bar's right slot — a short label, and somewhere for it to go. */
export interface PageMobileAction {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface Heading {
  title: string;
  url: string;
  /**
   * Url of the sidebar section this page belongs to, for pages whose own path
   * sits outside it — permissions screens live under `/permissions/...` but
   * are reached from, and belong to, Users. Resolved against the *visible*
   * menu, so a section the viewer cannot open is simply not shown.
   */
  section?: string;
  /** Href for the phone bar's back chevron, which replaces the hamburger. */
  back?: string;
  /** Render the phone bar's title in the mono face (task names, ids). */
  mono?: boolean;
  mobileAction?: PageMobileAction;
}

const HeadingValue = createContext<Heading | null>(null);
const HeadingSetter = createContext<((heading: Heading) => void) | null>(null);

export function PageHeadingProvider({ children }: { children: React.ReactNode }) {
  const [heading, setHeading] = useState<Heading | null>(null);
  return (
    <HeadingSetter.Provider value={setHeading}>
      <HeadingValue.Provider value={heading}>{children}</HeadingValue.Provider>
    </HeadingSetter.Provider>
  );
}

/** Everything the current page told the shell about itself, or null. */
export function usePageChrome(currentUrl: string): Heading | null {
  const heading = useContext(HeadingValue);
  return heading && heading.url === currentUrl ? heading : null;
}

/** The current page's heading, or null when it hasn't reported one. */
export function usePageHeading(currentUrl: string): string | null {
  return usePageChrome(currentUrl)?.title ?? null;
}

/** The section url this page declared, if any. */
export function usePageSection(currentUrl: string): string | null {
  return usePageChrome(currentUrl)?.section ?? null;
}

/** Report this page's heading to the shell. No-op outside a provider. */
export function useReportPageHeading(heading: Omit<Heading, 'url'>): void;
/** Positional form kept for pages that only ever had a title and a section. */
export function useReportPageHeading(title: string, section?: string): void;
export function useReportPageHeading(
  headingOrTitle: Omit<Heading, 'url'> | string,
  positionalSection?: string,
): void {
  const setHeading = useContext(HeadingSetter);
  const url = usePage().url;
  const declared =
    typeof headingOrTitle === 'string'
      ? { title: headingOrTitle, section: positionalSection }
      : headingOrTitle;
  const { title, section, back, mono } = declared;
  const action = declared.mobileAction;
  const actionLabel = action?.label;
  const actionHref = action?.href;
  const hasOnClick = Boolean(action?.onClick);
  // A page re-creates its handler on every render. Keying the report on it
  // would publish a new heading each time, re-render the provider, and loop —
  // so the latest handler is read through a ref and the published wrapper
  // stays identical across renders.
  const onClickRef = useRef(action?.onClick);
  onClickRef.current = action?.onClick;
  const next = useMemo<Heading>(
    () => ({
      title,
      url,
      section,
      back,
      mono,
      mobileAction: actionLabel
        ? {
            label: actionLabel,
            href: actionHref,
            onClick: hasOnClick ? () => onClickRef.current?.() : undefined,
          }
        : undefined,
    }),
    [title, url, section, back, mono, actionLabel, actionHref, hasOnClick],
  );
  useEffect(() => {
    setHeading?.(next);
  }, [setHeading, next]);
}
