import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const URL = '/admin/background-tasks/7';

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({ url: URL, props: {} }),
  Link: ({
    href,
    children,
    ...rest
  }: { href: string; children: React.ReactNode } & Record<string, unknown>) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('@simple-module-py/i18n', () => {
  const labels: Record<string, string> = {
    'ui.sidebar.open': 'Open sidebar',
    'ui.sidebar.back': 'Back',
  };
  return {
    useT: () => ({ t: (key: string) => labels[key] ?? key }),
    keys: { ui: { sidebar: { open: 'ui.sidebar.open', back: 'ui.sidebar.back' } } },
  };
});

import { PageHeadingProvider, useReportPageHeading } from '../components/page-heading';
import { MobileBar } from './MobileBar';
import { DEFAULT_SIDEBAR_THEME } from './sidebar-theme';

const THEME = { ...DEFAULT_SIDEBAR_THEME, mobileTitleLabel: 'SimpleModule' };
const USER = { name: 'Ada Rowe', email: 'ada@example.com', roles: ['admin'] };

function Page({ heading }: { heading: Parameters<typeof useReportPageHeading>[0] }) {
  useReportPageHeading(heading as never);
  return null;
}

function bar(extra: Partial<React.ComponentProps<typeof MobileBar>> = {}) {
  return (
    <MobileBar
      theme={THEME}
      appName="Acme Admin"
      currentUrl={URL}
      user={USER}
      onOpen={() => {}}
      {...extra}
    />
  );
}

describe('MobileBar', () => {
  it('falls back to the app name and the hamburger before a page reports', () => {
    const onOpen = vi.fn();
    render(<PageHeadingProvider>{bar({ onOpen })}</PageHeadingProvider>);
    expect(screen.getByText('Acme Admin')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open sidebar' }));
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('shows the page title and the user’s initials', () => {
    render(
      <PageHeadingProvider>
        <Page heading={{ title: 'Dashboard' }} />
        {bar()}
      </PageHeadingProvider>,
    );
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('AR')).toBeInTheDocument();
    expect(screen.queryByText('Acme Admin')).toBeNull();
  });

  it('swaps the hamburger for a back link when the page declares one', () => {
    render(
      <PageHeadingProvider>
        <Page
          heading={{ title: 'generate_thumbnail', back: '/admin/background-tasks', mono: true }}
        />
        {bar()}
      </PageHeadingProvider>,
    );
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute(
      'href',
      '/admin/background-tasks',
    );
    expect(screen.queryByRole('button', { name: 'Open sidebar' })).toBeNull();
    expect(screen.getByText('generate_thumbnail')).toHaveClass('font-mono');
  });

  it('renders the page’s mobile action instead of the avatar', () => {
    render(
      <PageHeadingProvider>
        <Page
          heading={{ title: 'Users', mobileAction: { label: '+ Add', href: '/admin/users/add' } }}
        />
        {bar()}
      </PageHeadingProvider>,
    );
    expect(screen.getByRole('link', { name: '+ Add' })).toHaveAttribute('href', '/admin/users/add');
    expect(screen.queryByText('AR')).toBeNull();
  });

  it('runs an onClick mobile action', () => {
    const onClick = vi.fn();
    render(
      <PageHeadingProvider>
        <Page heading={{ title: 'Files', mobileAction: { label: 'Upload', onClick } }} />
        {bar()}
      </PageHeadingProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
