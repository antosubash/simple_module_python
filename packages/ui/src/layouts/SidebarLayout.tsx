import { Link, usePage } from '@inertiajs/react';
import { Avatar, AvatarFallback } from '@ui/components/ui/avatar';
import { Button } from '@ui/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@ui/components/ui/tooltip';
import type React from 'react';
import { useState } from 'react';
import { NavIcon } from '../components/NavIcon';
import type { SharedProps } from '../types';

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
  const { auth, menus } = page.props as unknown as SharedProps;
  const currentUrl = page.url;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = () => setSidebarOpen(false);

  const menuItems = menus?.[menuKey] ?? [];

  return (
    <TooltipProvider>
      <div className="min-h-screen bg-background">
        {/* Mobile top bar */}
        <div
          className={`sticky top-0 z-40 flex h-14 items-center gap-3 ${theme.sidebarBg} px-4 lg:hidden`}
        >
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setSidebarOpen(true)}
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
          <Link href="/dashboard" className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-md ${theme.accentColor} flex items-center justify-center shadow-sm`}
            >
              <span className="text-white font-bold text-xs font-[var(--font-display)]">SM</span>
            </div>
            <span className="text-base font-semibold text-white font-[var(--font-display)]">
              {theme.mobileTitleLabel}
            </span>
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
            <Link href="/dashboard" className="flex items-center gap-2.5 group">
              <div
                className={`w-8 h-8 rounded-lg ${theme.accentColor} flex items-center justify-center shadow-lg shadow-primary-500/15 transition-transform duration-200 group-hover:scale-105`}
              >
                <span className="text-white font-bold text-sm font-[var(--font-display)]">SM</span>
              </div>
              <span className="text-lg font-semibold text-white font-[var(--font-display)] tracking-tight">
                SimpleModule
              </span>
            </Link>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={closeSidebar}
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
          <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
            {menuItems.map((item, index) => {
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
            {footerNavSlot}
          </nav>

          {/* User section */}
          {auth?.user && (
            <div className="px-3 py-4 border-t border-white/[0.06]">
              <div className="flex items-center gap-3 px-3 py-2">
                <Avatar className="ring-2 ring-primary-500/20">
                  <AvatarFallback className={`${theme.avatarBg} text-white text-xs`}>
                    {auth.user.name?.charAt(0)?.toUpperCase() || 'U'}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{auth.user.name}</p>
                  <p className={`text-xs truncate ${theme.mutedTextClass}`}>{auth.user.email}</p>
                </div>
              </div>
              {menus?.userDropdown?.map((item) => (
                <a
                  key={item.url}
                  href={item.url}
                  onClick={closeSidebar}
                  className={`flex items-center gap-3 px-3 py-2 mt-1 rounded-lg text-sm ${theme.mutedTextClass} hover:text-white ${theme.hoverBg} transition-colors`}
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </a>
              ))}
            </div>
          )}
        </aside>

        {/* Main content */}
        <main className="min-h-screen lg:ml-64">{children}</main>
      </div>
    </TooltipProvider>
  );
}
