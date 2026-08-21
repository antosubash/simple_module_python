import { Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Menu, X } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { BrandingBanner } from '../components/BrandingBanner';
import { BrandingFooter } from '../components/BrandingFooter';
import { BrandingHead } from '../components/BrandingHead';
import { LocaleSwitcher } from '../components/LocaleSwitcher';
import { LOGIN_PATH, REGISTER_PATH } from '../lib/auth-routes';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME, BRAND_REPO_URL } from '../lib/brand';
import type { SharedProps } from '../types';

export function PublicLayout({ children }: { children: React.ReactNode }) {
  const { t } = useT();
  const { auth, branding, signup } = usePage<{ props: SharedProps }>()
    .props as unknown as SharedProps;
  const [menuOpen, setMenuOpen] = useState(false);
  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;
  const logoUrl = branding?.logoUrl ?? null;
  const brandInitial = appName.trim().charAt(0).toUpperCase() || 'S';

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <BrandingHead />
      <BrandingBanner />
      <nav className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-8 sm:py-3.5">
          <div className="flex items-center justify-between">
            <Link href="/" className="group flex items-center gap-2.5">
              {logoUrl ? (
                <img
                  src={logoUrl}
                  alt={appName}
                  className="h-8 w-8 rounded-lg object-contain shadow-md transition-transform group-hover:scale-105"
                />
              ) : (
                <div
                  className={`flex h-8 w-8 items-center justify-center rounded-lg ${BRAND_ACCENT} shadow-md shadow-primary-600/30 transition-transform group-hover:scale-105`}
                >
                  <span className="font-bold text-white text-sm font-[var(--font-display)]">
                    {brandInitial}
                  </span>
                </div>
              )}
              <span className="text-[15px] font-bold tracking-tight font-[var(--font-display)]">
                {appName}
              </span>
            </Link>

            <div className="hidden items-center gap-4 sm:flex">
              <a
                href={`${BRAND_REPO_URL}#readme`}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {t(keys.ui.public_nav.docs)}
              </a>
              <a
                href={`${BRAND_REPO_URL}/tree/main/modules`}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {t(keys.ui.public_nav.modules)}
              </a>
              <a
                href={BRAND_REPO_URL}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {t(keys.ui.public_nav.github)}
              </a>
              <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />
              <LocaleSwitcher />
              {auth?.isAuthenticated ? (
                <Button asChild size="sm">
                  <a href="/dashboard/">{t(keys.ui.public_nav.open_dashboard)}</a>
                </Button>
              ) : (
                <>
                  <Button asChild variant={signup?.allowed ? 'ghost' : 'default'} size="sm">
                    <a href={LOGIN_PATH}>{t(keys.ui.public_nav.log_in)}</a>
                  </Button>
                  {signup?.allowed && (
                    <Button asChild size="sm">
                      <a href={REGISTER_PATH}>{t(keys.ui.public_nav.sign_up)}</a>
                    </Button>
                  )}
                </>
              )}
            </div>

            <button
              type="button"
              onClick={() => setMenuOpen((prev) => !prev)}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground sm:hidden"
              aria-label={
                menuOpen ? t(keys.ui.public_nav.close_menu) : t(keys.ui.public_nav.open_menu)
              }
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>

          {menuOpen && (
            <div className="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:hidden">
              {auth?.isAuthenticated ? (
                <Button asChild className="w-full">
                  <a href="/dashboard/">{t(keys.ui.public_nav.open_dashboard)}</a>
                </Button>
              ) : (
                <>
                  {signup?.allowed && (
                    <Button asChild className="w-full">
                      <a href={REGISTER_PATH}>{t(keys.ui.public_nav.sign_up)}</a>
                    </Button>
                  )}
                  <Button
                    asChild
                    variant={signup?.allowed ? 'outline' : 'default'}
                    className="w-full"
                  >
                    <a href={LOGIN_PATH}>{t(keys.ui.public_nav.log_in)}</a>
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </nav>

      <main className="flex-1">{children}</main>

      <BrandingFooter
        appName={appName}
        logoUrl={logoUrl}
        variant="public"
        footer={branding?.footer ?? null}
      />
    </div>
  );
}
