import { Link, usePage } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Menu, X } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { LocaleSwitcher } from '../components/LocaleSwitcher';
import type { SharedProps } from '../types';

export function PublicLayout({ children }: { children: React.ReactNode }) {
  const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-8 sm:py-3.5">
          <div className="flex items-center justify-between">
            <Link href="/" className="group flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary-600 to-primary-800 shadow-md shadow-primary-600/30 transition-transform group-hover:scale-105">
                <span className="font-bold text-white text-sm font-[var(--font-display)]">S</span>
              </div>
              <div className="flex flex-col leading-tight">
                <span className="text-[15px] font-bold tracking-tight font-[var(--font-display)]">
                  simple_module
                </span>
                <span className="font-mono text-[10px] text-muted-foreground">python · v0.1</span>
              </div>
            </Link>

            <div className="hidden items-center gap-4 sm:flex">
              <a
                href="https://github.com/antosubash/simple_module_python#readme"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Docs
              </a>
              <a
                href="https://github.com/antosubash/simple_module_python/tree/main/modules"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Modules
              </a>
              <a
                href="https://github.com/antosubash/simple_module_python"
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                GitHub
              </a>
              <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
              <LocaleSwitcher />
              {auth?.isAuthenticated ? (
                <Button asChild size="sm">
                  <a href="/dashboard/">Open Dashboard</a>
                </Button>
              ) : (
                <>
                  <Button asChild variant="ghost" size="sm">
                    <a href="/auth/login">Log in</a>
                  </Button>
                  <Button asChild size="sm">
                    <a href="/auth/login">Sign up</a>
                  </Button>
                </>
              )}
            </div>

            <button
              type="button"
              onClick={() => setMenuOpen((prev) => !prev)}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground sm:hidden"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>

          {menuOpen && (
            <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:hidden">
              {auth?.isAuthenticated ? (
                <Button asChild className="w-full">
                  <a href="/dashboard/">Open Dashboard</a>
                </Button>
              ) : (
                <>
                  <Button asChild className="w-full">
                    <a href="/auth/login">Sign up</a>
                  </Button>
                  <Button asChild variant="outline" className="w-full">
                    <a href="/auth/login">Log in</a>
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </nav>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-border bg-background py-6 px-4 sm:px-8">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-gradient-to-br from-primary-600 to-primary-800">
              <span className="font-bold text-white text-[10px] font-[var(--font-display)]">S</span>
            </div>
            <span className="font-mono text-xs text-muted-foreground">
              simple_module_python · MIT
            </span>
          </div>
          <div className="flex gap-5 text-xs text-muted-foreground">
            <a
              href="https://github.com/antosubash/simple_module_python#readme"
              className="hover:text-foreground transition-colors"
            >
              Docs
            </a>
            <a
              href="https://github.com/antosubash/simple_module_python/releases"
              className="hover:text-foreground transition-colors"
            >
              Changelog
            </a>
            <a
              href="https://github.com/antosubash/simple_module_python"
              className="hover:text-foreground transition-colors"
            >
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
