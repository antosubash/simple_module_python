import { Link, usePage } from '@inertiajs/react';
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
    <div className="min-h-screen bg-gray-50">
      <div
        className={`sticky top-0 z-40 flex h-14 items-center gap-3 ${theme.sidebarBg} px-4 lg:hidden`}
      >
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className={`p-1.5 rounded-lg text-gray-300 hover:text-white ${theme.hoverBg} transition-colors`}
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
        </button>
        <Link href="/dashboard" className="flex items-center gap-2">
          <div
            className={`w-7 h-7 rounded-md ${theme.accentColor} flex items-center justify-center`}
          >
            <span className="text-white font-bold text-xs">SM</span>
          </div>
          <span className="text-base font-semibold text-white">{theme.mobileTitleLabel}</span>
        </Link>
      </div>

      {sidebarOpen && (
        <button
          type="button"
          aria-label="Close sidebar"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden cursor-default"
          onClick={closeSidebar}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 ${theme.sidebarBg} flex flex-col border-r border-gray-800 transition-transform duration-200 ease-in-out lg:translate-x-0 lg:z-30 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <div className="h-14 lg:h-16 flex items-center justify-between px-4 lg:px-6 border-b border-white/10">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div
              className={`w-8 h-8 rounded-lg ${theme.accentColor} flex items-center justify-center`}
            >
              <span className="text-white font-bold text-sm">SM</span>
            </div>
            <span className="text-lg font-semibold text-white">SimpleModule</span>
          </Link>
          <button
            type="button"
            onClick={closeSidebar}
            className={`lg:hidden p-1.5 rounded-lg text-gray-400 hover:text-white ${theme.hoverBg} transition-colors`}
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
          </button>
        </div>

        {headerSlot}

        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {menuItems.map((item) => {
            const isActive = currentUrl.startsWith(item.url);
            return (
              <Link
                key={item.url}
                href={item.url}
                onClick={closeSidebar}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive ? theme.activeClass : theme.inactiveClass
                }`}
              >
                <NavIcon name={item.icon} />
                {item.label}
              </Link>
            );
          })}
          {footerNavSlot}
        </nav>

        {auth?.user && (
          <div className="px-3 py-4 border-t border-white/10">
            <div className="flex items-center gap-3 px-3 py-2">
              <div
                className={`w-8 h-8 rounded-full ${theme.avatarBg} flex items-center justify-center`}
              >
                <span className="text-xs font-medium text-white">
                  {auth.user.name?.charAt(0)?.toUpperCase() || 'U'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{auth.user.name}</p>
                <p className={`text-xs truncate ${theme.mutedTextClass}`}>{auth.user.email}</p>
              </div>
            </div>
            {menus?.userDropdown?.map((item) => (
              <Link
                key={item.url}
                href={item.url}
                onClick={closeSidebar}
                className={`flex items-center gap-3 px-3 py-2 mt-1 rounded-lg text-sm ${theme.mutedTextClass} hover:text-white ${theme.hoverBg} transition-colors`}
              >
                <NavIcon name={item.icon} />
                {item.label}
              </Link>
            ))}
          </div>
        )}
      </aside>

      <main className="min-h-screen lg:ml-64">{children}</main>
    </div>
  );
}
