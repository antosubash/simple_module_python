import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { BrandingFooter } from './BrandingFooter';

describe('BrandingFooter', () => {
  test('renders the app name and framework links', () => {
    render(<BrandingFooter appName="Acme" />);
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Docs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Changelog' })).toBeInTheDocument();
  });

  test('shows the current year and licence in the caption', () => {
    render(<BrandingFooter appName="Acme" />);
    const year = new Date().getFullYear();
    expect(screen.getByText(new RegExp(`${year}.*MIT`))).toBeInTheDocument();
  });

  test('renders host-configured links instead of the framework ones', () => {
    render(
      <BrandingFooter
        appName="Acme"
        links={[
          { label: 'Handbook', href: 'https://acme.example.org/handbook' },
          { label: 'Contact', href: '/contact' },
        ]}
      />,
    );
    expect(screen.getByRole('link', { name: 'Handbook' })).toHaveAttribute(
      'href',
      'https://acme.example.org/handbook',
    );
    expect(screen.getByRole('link', { name: 'Contact' })).toBeInTheDocument();
    // GH #282: the whole point is that the framework repo stops being advertised.
    expect(screen.queryByRole('link', { name: 'GitHub' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Changelog' })).not.toBeInTheDocument();
  });

  test.each([
    ['null', null],
    ['undefined', undefined],
    ['an empty list', []],
  ])('falls back to the framework links when links is %s', (_name, links) => {
    render(<BrandingFooter appName="Acme" links={links} />);
    expect(screen.getByRole('link', { name: 'Docs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'GitHub' })).toBeInTheDocument();
  });

  test('renders two links sharing a href', () => {
    // Nothing server-side enforces href uniqueness, so a href-keyed list would
    // collide here and reconcile unpredictably.
    render(
      <BrandingFooter
        appName="Acme"
        links={[
          { label: 'Docs', href: '/docs' },
          { label: 'Handbook', href: '/docs' },
        ]}
      />,
    );
    expect(screen.getByRole('link', { name: 'Docs' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Handbook' })).toBeInTheDocument();
  });

  test('renders the uploaded logo when a logoUrl is provided', () => {
    render(<BrandingFooter appName="Acme" logoUrl="/api/file-storage/files/abc/download" />);
    expect(screen.getByRole('img', { name: 'Acme' })).toHaveAttribute(
      'src',
      '/api/file-storage/files/abc/download',
    );
  });

  test('renders the host-configured footer text in place of the licence caption', () => {
    render(<BrandingFooter appName="Acme" footerText="© 2026 Acme Corp" />);
    expect(screen.getByText('© 2026 Acme Corp')).toBeInTheDocument();
    // GH #282's sibling: a deployment should stop advertising the framework's
    // licence as its own.
    expect(screen.queryByText(/MIT/)).not.toBeInTheDocument();
  });

  test.each([
    ['null', null],
    ['undefined', undefined],
    ['blank', '   '],
  ])('falls back to the licence caption when footerText is %s', (_name, footerText) => {
    render(<BrandingFooter appName="Acme" footerText={footerText} />);
    const year = new Date().getFullYear();
    expect(screen.getByText(new RegExp(`${year}.*MIT`))).toBeInTheDocument();
  });
});
