import { Link, usePage } from '@inertiajs/react';
import { Button } from '@simple-module/ui/components/ui/button';
import type React from 'react';
import { useState } from 'react';
import type { SharedProps } from '../types';

const NOISE_STYLE = {
  backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
} as const;

export function PublicLayout({ children }: { children: React.ReactNode }) {
  const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col bg-landing-bg text-white">
      {/* Subtle warm grain overlay */}
      <div className="fixed inset-0 pointer-events-none opacity-[0.03]" style={NOISE_STYLE} />

      <nav className="relative z-10 px-4 py-4 sm:px-8 sm:py-5">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-primary-400 to-primary-600 flex items-center justify-center shadow-lg shadow-primary-500/20 transition-transform duration-200 group-hover:scale-105">
              <span className="text-white font-bold text-sm font-[var(--font-display)]">SM</span>
            </div>
            <span className="text-xl font-bold font-[var(--font-display)] tracking-tight">
              SimpleModule
            </span>
          </Link>

          <div className="hidden sm:flex items-center gap-3">
            {auth?.isAuthenticated ? (
              <Button asChild>
                <a href="/dashboard">Go to Dashboard</a>
              </Button>
            ) : (
              <>
                <Button
                  asChild
                  variant="ghost"
                  className="text-sidebar-icon hover:text-white hover:bg-white/10"
                >
                  <a href="/auth/login">Sign In</a>
                </Button>
                <Button asChild>
                  <a href="/auth/login">Get Started</a>
                </Button>
              </>
            )}
          </div>

          <button
            type="button"
            onClick={() => setMenuOpen((prev) => !prev)}
            className="sm:hidden p-2 rounded-lg text-sidebar-icon hover:text-white hover:bg-white/10 transition-colors"
          >
            {menuOpen ? (
              <svg
                aria-hidden="true"
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            ) : (
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
            )}
          </button>
        </div>

        {menuOpen && (
          <div className="sm:hidden mt-4 pt-4 border-t border-white/10 flex flex-col gap-3 max-w-6xl mx-auto">
            {auth?.isAuthenticated ? (
              <Button asChild className="w-full">
                <a href="/dashboard">Go to Dashboard</a>
              </Button>
            ) : (
              <>
                <Button asChild className="w-full">
                  <a href="/auth/login">Get Started</a>
                </Button>
                <Button
                  asChild
                  variant="ghost"
                  className="w-full text-sidebar-icon hover:text-white"
                >
                  <a href="/auth/login">Sign In</a>
                </Button>
              </>
            )}
          </div>
        )}
      </nav>

      <main className="relative z-10 flex-1">{children}</main>

      <footer className="relative z-10 border-t border-white/[0.06] py-6 px-4 text-center text-sm text-dark-text-subtle sm:py-8">
        <span className="font-[var(--font-display)]">SimpleModule</span> — Built with FastAPI,
        Inertia.js, React & Tailwind CSS
      </footer>
    </div>
  );
}
