import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({ usePage: () => ({ url: '/admin/background-tasks/7' }) }));

import { PageShell } from './PageShell';
import { PageHeadingProvider, usePageChrome, useReportPageHeading } from './page-heading';

const URL = '/admin/background-tasks/7';

/** Reads back what the page reported, the way the shell's phone bar does. */
function Probe() {
  const chrome = usePageChrome(URL);
  if (!chrome) return <span data-testid="chrome">none</span>;
  return (
    <>
      <span data-testid="chrome">
        {[
          chrome.title,
          chrome.section ?? '-',
          chrome.back ?? '-',
          chrome.mono ? 'mono' : '-',
          chrome.mobileAction?.label ?? '-',
          chrome.mobileAction?.href ?? '-',
        ].join('|')}
      </span>
      {chrome.mobileAction?.onClick && (
        <button type="button" onClick={chrome.mobileAction.onClick}>
          run
        </button>
      )}
    </>
  );
}

describe('PageShell heading report', () => {
  it('reports back, mono and a mobile action alongside the title', () => {
    render(
      <PageHeadingProvider>
        <PageShell
          title="generate_thumbnail"
          section="/admin/background-tasks"
          back="/admin/background-tasks"
          mono
          mobileAction={{ label: '+ Add', href: '/admin/users/add' }}
        >
          body
        </PageShell>
        <Probe />
      </PageHeadingProvider>,
    );
    expect(screen.getByTestId('chrome')).toHaveTextContent(
      'generate_thumbnail|/admin/background-tasks|/admin/background-tasks|mono|+ Add|/admin/users/add',
    );
  });

  it('reports only the title when the page declares nothing else', () => {
    render(
      <PageHeadingProvider>
        <PageShell title="Dashboard">body</PageShell>
        <Probe />
      </PageHeadingProvider>,
    );
    expect(screen.getByTestId('chrome')).toHaveTextContent('Dashboard|-|-|-|-|-');
  });

  it('runs the page’s handler through the reported action', () => {
    const onClick = vi.fn();
    render(
      <PageHeadingProvider>
        <PageShell title="Users" mobileAction={{ label: '+ Add', onClick }}>
          body
        </PageShell>
        <Probe />
      </PageHeadingProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'run' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe('PageShell rendering', () => {
  it('renders leading, badge and a rich description beside the title', () => {
    render(
      <PageHeadingProvider>
        <PageShell
          title="dana@example.com"
          leading={<span data-testid="avatar">DR</span>}
          badge={<span data-testid="badge">active</span>}
          description={<em>Member since 2026</em>}
          titleClassName="font-mono"
        >
          body
        </PageShell>
      </PageHeadingProvider>,
    );
    expect(screen.getByTestId('avatar')).toBeInTheDocument();
    expect(screen.getByTestId('badge')).toBeInTheDocument();
    expect(screen.getByText('Member since 2026')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1 })).toHaveClass('font-mono');
  });
});

/** The pre-existing positional call every module page still uses. */
function LegacyPage() {
  useReportPageHeading('Role editor', '/admin/users');
  return null;
}

describe('useReportPageHeading positional overload', () => {
  it('still reports title and section', () => {
    render(
      <PageHeadingProvider>
        <LegacyPage />
        <Probe />
      </PageHeadingProvider>,
    );
    expect(screen.getByTestId('chrome')).toHaveTextContent('Role editor|/admin/users|-|-|-|-');
  });
});
