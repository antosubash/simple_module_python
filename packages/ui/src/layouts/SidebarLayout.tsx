import { Link, usePage } from '@inertiajs/react';
import { Avatar, AvatarFallback } from '@simple-module-py/ui/components/ui/avatar';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@simple-module-py/ui/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@simple-module-py/ui/components/ui/tooltip';
import { ChevronsUpDown } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { BrandingHead } from '../components/BrandingHead';
import { BrandingMark } from '../components/BrandingMark';
import { NavIcon } from '../components/NavIcon';
import type { MenuItem, SharedProps } from '../types';

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

export function SidebarLayout({
  children,
  menuKey,
  theme,
  headerSlot,
  footerNavSlot,
}: SidebarLayoutProps) {
  const page = usePage<{ props: SharedProps }>();
  const { auth, menus, branding } = page.props as unknown as SharedProps;
  const currentUrl = page.url;
  const appName = branding?.appName ?? theme.mobileTitleLabel;
  const logoUrl = branding?.logoUrl ?? null;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = () => setSidebarOpen(false);

  const menuItems = menus?.[menuKey] ?? [];

  return (
    <TooltipProvider>
      <BrandingHead />
      <div className="min-h-screen bg-background">
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
              logoUrl={logoUrl}
              accentColor={theme.accentColor}
              size="sm"
            />
          </Link>
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
                logoUrl={logoUrl}
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
                  const isActive = currentUrl.startsWith(item.url);
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
          {auth?.user &&
            (() => {
              // UserContext.from_user defaults ``name`` to ``email`` when no
              // full_name is set, so guard against rendering the email twice.
              const hasDistinctName = auth.user.name && auth.user.name !== auth.user.email;
              return (
                <div className="px-3 py-3 border-t border-white/[0.06]">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        className={`flex w-full items-center gap-3 px-2 py-2 rounded-lg text-left ${theme.hoverBg} transition-colors`}
                      >
                        <Avatar className="ring-2 ring-primary-500/20">
                          <AvatarFallback className={`${theme.avatarBg} text-white text-xs`}>
                            {(auth.user.name || auth.user.email)?.charAt(0)?.toUpperCase() || 'U'}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          {hasDistinctName ? (
                            <>
                              <p className="text-sm font-medium text-white truncate">
                                {auth.user.name}
                              </p>
                              <p className={`text-xs truncate ${theme.mutedTextClass}`}>
                                {auth.user.email}
                              </p>
                            </>
                          ) : (
                            <p className="text-sm font-medium text-white truncate">
                              {auth.user.email}
                            </p>
                          )}
                        </div>
                        <ChevronsUpDown
                          className={`w-4 h-4 shrink-0 ${theme.mutedTextClass}`}
                          aria-hidden="true"
                        />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent side="top" align="start" className="w-56">
                      <DropdownMenuLabel className="font-normal">
                        {hasDistinctName ? (
                          <>
                            <p className="text-sm font-medium truncate">{auth.user.name}</p>
                            <p className="text-xs text-muted-foreground truncate">
                              {auth.user.email}
                            </p>
                          </>
                        ) : (
                          <p className="text-sm font-medium truncate">{auth.user.email}</p>
                        )}
                      </DropdownMenuLabel>
                      {menus?.userDropdown && menus.userDropdown.length > 0 && (
                        <DropdownMenuSeparator />
                      )}
                      {menus?.userDropdown?.map((item) => (
                        <DropdownMenuItem key={item.url} asChild onSelect={closeSidebar}>
                          <Link
                            href={item.url}
                            method={item.method === 'post' ? 'post' : 'get'}
                            as={item.method === 'post' ? 'button' : 'a'}
                            className="flex w-full items-center gap-2"
                          >
                            <NavIcon name={item.icon} />
                            {item.label}
                          </Link>
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              );
            })()}
        </aside>

        {/* Main content */}
        <main className="min-h-screen lg:ml-64">{children}</main>
      </div>
    </TooltipProvider>
  );
}
