import { Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Menu, X } from 'lucide-react';
import type React from 'react';
import { useEffect, useRef, useState } from 'react';
import { activeSection } from '../components/AppTopbar';
import { BrandingBanner } from '../components/BrandingBanner';
import { BrandingFooter } from '../components/BrandingFooter';
import { BrandingHead } from '../components/BrandingHead';
import { LocaleSwitcher } from '../components/LocaleSwitcher';
import { NavIcon } from '../components/NavIcon';
import { usePageProps } from '../hooks/usePageProps';
import { LOGIN_PATH } from '../lib/auth-routes';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME } from '../lib/brand';
import { useHomeUrl } from '../lib/home-url';
import { isPostMenuItem } from '../types';

export function PublicLayout({ children }: { children: React.ReactNode }) {
  const { t } = useT();
  const { auth, branding, menus } = usePageProps();
  const homeUrl = useHomeUrl();
  const { url } = usePage();
  const toggleRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const navbar = menus?.navbar ?? [];
  const active = activeSection(
    navbar.filter((item) => !isPostMenuItem(item) && /^\/(?!\/)/.test(item.url)),
    url,
  );
  const closeMenu = () => {
    if (mobileMenuRef.current?.contains(document.activeElement)) {
      toggleRef.current?.focus();
    }
    setMenuOpen(false);
  };
  // Escape closes the open mobile menu from anywhere on the page.
  // biome-ignore lint/correctness/useExhaustiveDependencies: closeMenu only reads refs.
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen]);
  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;
  const logoUrl = branding?.logoUrl ?? null;
  const brandInitial = appName.trim().charAt(0).toUpperCase() || 'S';
  // One button, two states. The nav used to fan out over `signup.allowed`
  // into Log in / Sign up / Open Dashboard, which advertised an account on a
  // closed instance and made the public entry point look like a decision.
  // A visitor either has a session or does not; nothing else belongs here.
  const entry = auth?.isAuthenticated
    ? { href: homeUrl, labelKey: keys.ui.public_nav.open_dashboard }
    : { href: LOGIN_PATH, labelKey: keys.ui.public_nav.sign_in };

  const renderNavbar = (mobile: boolean) =>
    navbar.map((item) => {
      const isActive = item === active;
      const className = `inline-flex items-center gap-2 text-sm transition-colors hover:text-foreground ${isActive ? 'text-foreground font-medium' : 'text-muted-foreground'} ${mobile ? 'min-h-11' : ''}`;
      const onClick = mobile ? closeMenu : undefined;
      const content = (
        <>
          {item.icon && <NavIcon name={item.icon} className="size-4" />}
          {item.label}
        </>
      );
      return isPostMenuItem(item) ? (
        <Link
          key={item.url}
          href={item.url}
          method="post"
          as="button"
          className={className}
          onClick={onClick}
        >
          {content}
        </Link>
      ) : (
        <a
          key={item.url}
          href={item.url}
          className={className}
          aria-current={isActive ? 'page' : undefined}
          onClick={onClick}
        >
          {content}
        </a>
      );
    });

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <BrandingHead />
      <BrandingBanner />
      <nav className="sticky top-0 z-50 border-b border-border bg-background">
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
                  <span className="font-bold text-white text-sm font-display">{brandInitial}</span>
                </div>
              )}
              <span className="text-[15px] font-bold tracking-tight font-display">{appName}</span>
            </Link>

            <div className="hidden items-center gap-4 sm:flex">
              {renderNavbar(false)}
              {navbar.length > 0 && <span className="mx-1 h-5 w-px bg-border" aria-hidden="true" />}
              <LocaleSwitcher />
              <Button asChild variant="outline" size="sm">
                <a href={entry.href}>{t(entry.labelKey)}</a>
              </Button>
            </div>

            <button
              ref={toggleRef}
              type="button"
              onClick={() => setMenuOpen((prev) => !prev)}
              aria-expanded={menuOpen}
              className="flex min-h-11 min-w-11 -mr-2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground sm:hidden"
              aria-label={
                menuOpen ? t(keys.ui.public_nav.close_menu) : t(keys.ui.public_nav.open_menu)
              }
            >
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>

          {menuOpen && (
            <div
              ref={mobileMenuRef}
              className="mt-4 flex flex-col gap-2 border-t border-border pt-4 sm:hidden"
            >
              {renderNavbar(true)}
              <Button asChild variant="outline" className="w-full min-h-11">
                <a href={entry.href} onClick={closeMenu}>
                  {t(entry.labelKey)}
                </a>
              </Button>
            </div>
          )}
        </div>
      </nav>

      <main className="flex-1">{children}</main>

      <BrandingFooter
        appName={appName}
        logoUrl={logoUrl}
        links={branding?.footerLinks}
        footerText={branding?.footerText}
        variant="public"
      />
    </div>
  );
}
