import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@simple-module-py/ui/components/ui/breadcrumb';
import { isUnder, samePath, trimmed } from '../lib/current-path';
import { isPostMenuItem, type MenuItem } from '../types';
import { CommandPalette } from './CommandPalette';
import { LocaleSwitcher } from './LocaleSwitcher';
import { usePageHeading } from './page-heading';

interface AppTopbarProps {
  navItems: MenuItem[];
  accountItems: MenuItem[];
  currentUrl: string;
  /**
   * Pre-resolved active section — the sidebar needs the same answer to
   * highlight its own entry, so it resolves it once (via `activeSection` /
   * `findSection` below) and passes the result down instead of AppTopbar
   * walking `navItems` a second time for the same render.
   */
  activeMenuItem: MenuItem | null;
}

/**
 * Which sidebar entry the current url belongs to.
 *
 * Longest match wins: `/users/admin/add` sits under `/users/admin`, and a
 * shorter entry that happens to share a prefix must not claim it.
 */
export function activeSection(items: MenuItem[], url: string): MenuItem | null {
  let best: MenuItem | null = null;
  for (const item of items) {
    if (!isUnder(url, item.url)) continue;
    // Compare the same normalized (trailing-slash-trimmed) path that isUnder
    // itself matched on — comparing raw string length here would let a lone
    // trailing slash outweigh a real path segment and pick the wrong item.
    if (!best || trimmed(item.url).length > trimmed(best.url).length) best = item;
  }
  return best;
}

/** Resolve a declared section url against the menu the viewer can actually see. */
export function findSection(items: MenuItem[], sectionUrl: string | null): MenuItem | null {
  if (!sectionUrl) return null;
  return items.find((item) => samePath(item.url, sectionUrl)) ?? null;
}

/**
 * The bar above every app screen: where you are, and how to get anywhere else.
 *
 * Desktop only. Below `lg` the sidebar collapses behind a hamburger and the
 * mobile bar already carries the brand and the locale control; stacking a
 * second 56px strip under it would spend a tenth of a phone screen restating
 * the heading that is about to be rendered directly beneath it.
 */
export function AppTopbar({ navItems, accountItems, currentUrl, activeMenuItem }: AppTopbarProps) {
  const { t } = useT();
  const heading = usePageHeading(currentUrl);
  // Signing out was reachable only from the avatar dropdown and ⌘K. The item
  // itself stays registry-owned — whichever auth provider is installed
  // contributes the one account entry that must be POSTed.
  const logout = accountItems.find(isPostMenuItem);
  const section = activeMenuItem;
  // Only a genuine sub-page earns a second crumb — on a section's own index the
  // heading and the section name are the same word, and "Users / Users" is noise.
  // This is a naming convention, not a guarantee: a sub-page whose title equals
  // its section's menu label would collapse to one crumb too. Title your
  // sub-pages more specifically than their section.
  const leaf = heading && heading !== section?.label ? heading : null;

  return (
    <header className="sticky top-0 z-20 hidden h-[var(--app-chrome-h)] shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-7 lg:flex">
      <Breadcrumb>
        <BreadcrumbList className="text-[13px]">
          {section ? (
            <>
              <BreadcrumbItem>
                {leaf ? (
                  <BreadcrumbLink asChild>
                    <Link href={section.url}>{section.label}</Link>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage>{section.label}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {leaf && (
                <>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{leaf}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
            </>
          ) : (
            heading && (
              <BreadcrumbItem>
                <BreadcrumbPage>{heading}</BreadcrumbPage>
              </BreadcrumbItem>
            )
          )}
        </BreadcrumbList>
      </Breadcrumb>

      <div className="flex items-center gap-3">
        <CommandPalette navItems={navItems} accountItems={accountItems} />
        <LocaleSwitcher />
        {logout && (
          <Link
            href={logout.url}
            method="post"
            as="button"
            className="inline-flex items-center rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
          >
            {t(keys.ui.topbar.log_out)}
          </Link>
        )}
      </div>
    </header>
  );
}
