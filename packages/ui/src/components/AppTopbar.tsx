import { Link } from '@inertiajs/react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@simple-module-py/ui/components/ui/breadcrumb';
import { isUnder, samePath, trimmed } from '../lib/current-path';
import type { MenuItem } from '../types';
import { CommandPalette } from './CommandPalette';
import { LocaleSwitcher } from './LocaleSwitcher';
import { usePageHeading, usePageSection } from './page-heading';

interface AppTopbarProps {
  navItems: MenuItem[];
  accountItems: MenuItem[];
  currentUrl: string;
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
export function AppTopbar({ navItems, accountItems, currentUrl }: AppTopbarProps) {
  const heading = usePageHeading(currentUrl);
  const declared = usePageSection(currentUrl);
  // Url match first; a declared section only fills the gap for pages that sit
  // outside their section's path. Looked up in the menu the viewer can see, so
  // it never offers a parent they'd be refused at.
  const section = activeSection(navItems, currentUrl) ?? findSection(navItems, declared);
  // Only a genuine sub-page earns a second crumb — on a section's own index the
  // heading and the section name are the same word, and "Users / Users" is noise.
  const leaf = heading && heading !== section?.label ? heading : null;

  return (
    <header className="sticky top-0 z-20 hidden h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-6 lg:flex">
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

      <div className="flex items-center gap-2">
        <CommandPalette navItems={navItems} accountItems={accountItems} />
        <LocaleSwitcher />
      </div>
    </header>
  );
}
