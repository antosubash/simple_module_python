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

  test('renders the uploaded logo when a logoUrl is provided', () => {
    render(<BrandingFooter appName="Acme" logoUrl="/api/file-storage/files/abc/download" />);
    expect(screen.getByRole('img', { name: 'Acme' })).toHaveAttribute(
      'src',
      '/api/file-storage/files/abc/download',
    );
  });
});
