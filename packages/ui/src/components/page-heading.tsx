import { usePage } from '@inertiajs/react';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';

/**
 * Lets the app shell name the page currently rendered inside it.
 *
 * The breadcrumb lives in the topbar, which the layout owns, but the only
 * component that knows what the page is called is the page's own `PageShell`
 * — several levels below. Rather than restate every title in a route table
 * (which then drifts from the heading on screen), `PageShell` reports the one
 * it is already rendering and the shell reads it back.
 *
 * The report carries the url it was made from, so a heading is only ever used
 * for the page it came from: during an Inertia swap the layout re-renders with
 * the new url before the incoming page's effect runs, and a bare string would
 * show the previous page's title against the new section for a frame.
 */

interface Heading {
  title: string;
  url: string;
  /**
   * Url of the sidebar section this page belongs to, for pages whose own path
   * sits outside it — permissions screens live under `/permissions/...` but
   * are reached from, and belong to, Users. Resolved against the *visible*
   * menu, so a section the viewer cannot open is simply not shown.
   */
  section?: string;
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

/** The current page's heading, or null when it hasn't reported one. */
export function usePageHeading(currentUrl: string): string | null {
  const heading = useContext(HeadingValue);
  return heading && heading.url === currentUrl ? heading.title : null;
}

/** The section url this page declared, if any. */
export function usePageSection(currentUrl: string): string | null {
  const heading = useContext(HeadingValue);
  return heading && heading.url === currentUrl ? (heading.section ?? null) : null;
}

/** Report this page's heading to the shell. No-op outside a provider. */
export function useReportPageHeading(title: string, section?: string): void {
  const setHeading = useContext(HeadingSetter);
  const url = usePage().url;
  const next = useMemo(() => ({ title, url, section }), [title, url, section]);
  useEffect(() => {
    setHeading?.(next);
  }, [setHeading, next]);
}
