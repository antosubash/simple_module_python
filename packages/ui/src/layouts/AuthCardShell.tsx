import { usePage } from '@inertiajs/react';
import type React from 'react';
import { BrandingHead } from '../components/BrandingHead';
import { BrandingMark } from '../components/BrandingMark';
import { BRAND_TECH } from '../lib/brand';
import type { SharedProps } from '../types';

/**
 * Full-viewport centered shell for unauthenticated flows
 * (login, register, password reset, email verify, invite accept).
 *
 * Light surface with emerald mesh blobs and a glass card — matches the
 * SimpleModulePython HiFi auth screens.
 */
export function AuthCardShell({ children }: { children: React.ReactNode }) {
  const { branding } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const appName = branding?.appName ?? 'SimpleModule';
  const logoUrl = branding?.logoUrl ?? null;

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
            <BrandingMark
              appName={appName}
              logoUrl={logoUrl}
              accentColor="bg-gradient-to-br from-primary-600 to-primary-800"
              labelClassName="text-[17px] font-bold tracking-tight font-[var(--font-display)] text-foreground"
              caption={BRAND_TECH}
            />
          </div>
          {children}
        </div>
      </div>
    </main>
  );
}
