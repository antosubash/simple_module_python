import { Link, usePage } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@simple-module-py/ui/components/ui/tooltip';
import type React from 'react';
import { useState } from 'react';
import { AppTopbar, activeSection, findSection } from '../components/AppTopbar';
import { BrandingBanner } from '../components/BrandingBanner';
import { BrandingFooter } from '../components/BrandingFooter';
import { BrandingHead } from '../components/BrandingHead';
import { BrandingMark } from '../components/BrandingMark';
import { LocaleSwitcher } from '../components/LocaleSwitcher';
import { NavIcon } from '../components/NavIcon';
import { PageHeadingProvider, usePageSection } from '../components/page-heading';
import { darkSurfaceLogo } from '../lib/brand';
import type { MenuItem, SharedProps } from '../types';
import { SidebarUserMenu } from './SidebarUserMenu';

function groupMenuItems(items: MenuItem[]): { group: string; items: MenuItem[] }[] {
  const groups: { group: string; items: MenuItem[] }[] = [];
  const indexByGroup = new Map<string, number>();
  for (const item of items) {
    const key = item.group ?? '';
    let idx = indexByGroup.get(key);
    if (idx === undefined) {
      idx = groups.length;
      indexByGroup.set(key, idx);
      groups.push({ group: key, items: [] });
    }
    groups[idx].items.push(item);
  }
  return groups;
}

interface SidebarTheme {
  sidebarBg: string;
  accentColor: string;
  avatarBg: string;
  hoverBg: string;
  activeClass: string;
  inactiveClass: string;
  mutedTextClass: string;
  mobileTitleLabel: string;
}

interface SidebarLayoutProps {
  children: React.ReactNode;
  menuKey: 'sidebar' | 'adminSidebar';
  theme: SidebarTheme;
  headerSlot?: React.ReactNode;
  footerNavSlot?: React.ReactNode;
}

/**
 * Thin wrapper so the shell itself sits *inside* the heading provider — the
 * sidebar reads the section a page declares, which it cannot do from the same
 * component that renders the provider.
 */
export function SidebarLayout(props: SidebarLayoutProps) {
  return (
    <PageHeadingProvider>
      <SidebarShell {...props} />
    </PageHeadingProvider>
  );
}

function SidebarShell({ children, menuKey, theme, headerSlot, footerNavSlot }: SidebarLayoutProps) {
  const page = usePage<{ props: SharedProps }>();
  const { auth, menus, branding } = page.props as unknown as SharedProps;
  const currentUrl = page.url;
  const appName = branding?.appName ?? theme.mobileTitleLabel;
  const logoUrl = branding?.logoUrl ?? null;
  // The sidebar and mobile bar are near-black whatever the theme, so they take
  // the dark logo variant when one exists. The footer sits on `bg-background`
  // and follows the theme, so it keeps the primary logo.
  const darkLogoUrl = darkSurfaceLogo(branding);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = () => setSidebarOpen(false);

  const menuItems = menus?.[menuKey] ?? [];
  const declaredSection = usePageSection(currentUrl);
  // Same "which entry does this page belong to" resolution AppTopbar uses for
  // the breadcrumb, so the sidebar highlight and the breadcrumb never disagree.
  const active = activeSection(menuItems, currentUrl) ?? findSection(menuItems, declaredSection);

  return (
    <TooltipProvider>
      <BrandingHead />
      <BrandingBanner />
      {/* --app-chrome-h names the height of the bar above the content — the
          topbar on lg, the mobile bar below it, both h-14 and mutually
          exclusive. Pages that must fill the viewport subtract it instead of
          hardcoding the pixel value. */}
      <div className="min-h-screen bg-background [--app-chrome-h:3.5rem]">
        {/* Mobile top bar */}
        <div
          className={`sticky top-0 z-40 flex h-14 items-center gap-3 ${theme.sidebarBg} px-4 lg:hidden`}
        >
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
            className="text-sidebar-icon hover:text-white hover:bg-white/10"
          >
            <svg
              aria-hidden="true"
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
              />
            </svg>
          </Button>
          <Link href="/dashboard/" className="flex items-center gap-2">
            <BrandingMark
              appName={appName}
              logoUrl={darkLogoUrl}
              accentColor={theme.accentColor}
              size="sm"
            />
          </Link>
          {/* The topbar that normally carries this is desktop-only, so the
              mobile bar keeps the locale control rather than losing it. */}
          <div className="ml-auto">
            <LocaleSwitcher />
          </div>
        </div>

        {/* Mobile overlay */}
        {sidebarOpen && (
          <button
            type="button"
            aria-label="Close sidebar"
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden cursor-default"
            onClick={closeSidebar}
          />
        )}

        {/* Sidebar */}
        <aside
          className={`fixed inset-y-0 left-0 z-50 w-64 ${theme.sidebarBg} flex flex-col border-r border-white/[0.06] transition-transform duration-200 ease-in-out lg:translate-x-0 lg:z-30 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
        >
          {/* Logo */}
          <div className="h-14 lg:h-16 flex items-center justify-between px-4 lg:px-5 border-b border-white/[0.06]">
            <Link href="/dashboard/" className="flex items-center gap-2.5 group">
              <BrandingMark
                appName={appName}
                logoUrl={darkLogoUrl}
                accentColor={theme.accentColor}
                size="md"
              />
            </Link>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={closeSidebar}
              aria-label="Close sidebar"
              className="lg:hidden text-sidebar-icon-muted hover:text-white hover:bg-white/10"
            >
              <svg
                aria-hidden="true"
                className="w-5 h-5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </Button>
          </div>

          {headerSlot}

          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 overflow-y-auto">
            {groupMenuItems(menuItems).map((group, groupIndex) => (
              <div
                key={group.group || `__ungrouped_${groupIndex}`}
                className={groupIndex === 0 ? 'space-y-0.5' : 'mt-4 space-y-0.5'}
              >
                {group.group && (
                  <div
                    className={`px-3 pb-1 text-xs font-semibold uppercase tracking-wider ${theme.mutedTextClass}`}
                  >
                    {group.group}
                  </div>
                )}
                {group.items.map((item, index) => {
                  const isActive = active?.url === item.url;
                  return (
                    <Tooltip key={item.url}>
                      <TooltipTrigger asChild>
                        <Link
                          href={item.url}
                          onClick={closeSidebar}
                          className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                            isActive ? theme.activeClass : theme.inactiveClass
                          }`}
                          style={{ animationDelay: `${index * 50}ms` }}
                        >
                          <NavIcon name={item.icon} />
                          {item.label}
                        </Link>
                      </TooltipTrigger>
                      <TooltipContent side="right" className="lg:hidden">
                        {item.label}
                      </TooltipContent>
                    </Tooltip>
                  );
                })}
              </div>
            ))}
            {footerNavSlot}
          </nav>

          {/* User section — avatar row opens a dropdown with Profile / Logout / etc. */}
          {auth?.user && (
            <SidebarUserMenu
              user={auth.user}
              items={menus?.userDropdown ?? []}
              avatarBg={theme.avatarBg}
              hoverBg={theme.hoverBg}
              mutedTextClass={theme.mutedTextClass}
              onNavigate={closeSidebar}
            />
          )}
        </aside>

        {/* Main content */}
        <main className="flex min-h-screen flex-col lg:ml-64">
          <AppTopbar
            navItems={menuItems}
            accountItems={menus?.userDropdown ?? []}
            currentUrl={currentUrl}
          />
          <div className="flex-1">{children}</div>
          <BrandingFooter
            appName={appName}
            logoUrl={logoUrl}
            variant="app"
            footer={branding?.footer ?? null}
          />
        </main>
      </div>
    </TooltipProvider>
  );
}
