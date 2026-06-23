import type React from 'react';
import { BrandingHead } from '../components/BrandingHead';

/**
 * Full-viewport centered shell for unauthenticated flows
 * (login, register, password reset, email verify, invite accept).
 *
 * Light surface with emerald mesh blobs and a glass card — matches the
 * SimpleModulePython HiFi auth screens.
 */
export function AuthCardShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden bg-secondary/40 p-4">
      <BrandingHead />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-[10%] -right-[10%] h-[600px] w-[600px] rounded-full bg-primary-600 opacity-15 blur-[100px]" />
        <div className="absolute -bottom-[10%] -left-[10%] h-[500px] w-[500px] rounded-full bg-primary-800 opacity-15 blur-[100px]" />
      </div>
      <div className="relative w-full max-w-md">
        <div className="rounded-3xl border border-border bg-white/85 p-7 shadow-xl backdrop-blur-xl backdrop-saturate-150">
          <div className="mb-5 flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-primary-600 to-primary-800 shadow-md shadow-primary-600/30">
              <span className="font-bold text-white text-base font-[var(--font-display)]">S</span>
            </div>
            <div className="flex flex-col leading-tight">
              <span className="text-[17px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
                simple_module
              </span>
              <span className="font-mono text-[11px] text-muted-foreground">python</span>
            </div>
          </div>
          {children}
        </div>
      </div>
    </main>
  );
}
