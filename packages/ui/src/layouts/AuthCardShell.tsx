import type React from 'react';

const MAP_BG = `radial-gradient(ellipse at 30% 40%, oklch(0.92 0.03 155) 0%, transparent 35%),
  radial-gradient(ellipse at 70% 60%, oklch(0.88 0.04 200) 0%, transparent 40%),
  repeating-linear-gradient(45deg, transparent 0 14px, rgba(0,0,0,0.025) 14px 15px),
  repeating-linear-gradient(-45deg, transparent 0 14px, rgba(0,0,0,0.025) 14px 15px),
  oklch(0.93 0.005 250)`;

/**
 * Two-column shell for unauthenticated flows (login, register, password
 * reset, email verify, invite accept). Left column hosts the form;
 * right column is a quiet map placeholder that mirrors the LacoWiki
 * landing aesthetic. Falls back to a single-column layout under the lg
 * breakpoint so password-reset flows still read well on mobile.
 */
export function AuthCardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen grid-cols-1 bg-background lg:grid-cols-2">
      <div className="flex flex-col justify-center px-6 py-12 sm:px-12 lg:px-20">
        <div className="mx-auto w-full max-w-sm">
          <div className="mb-10 flex items-center gap-2.5">
            <div className="h-5 w-5 rounded bg-primary" />
            <span className="text-sm font-semibold tracking-tight">SimpleModule</span>
          </div>
          {children}
        </div>
      </div>
      <div
        className="hidden border-l border-border/60 lg:block"
        style={{ backgroundImage: MAP_BG }}
        aria-hidden="true"
      />
    </div>
  );
}
