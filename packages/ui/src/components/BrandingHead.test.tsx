import { cleanup, render } from '@testing-library/react';
import type React from 'react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

const state = vi.hoisted(() => ({ branding: undefined as unknown }));

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({ props: { branding: state.branding } }),
  Head: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import { BrandingHead } from './BrandingHead';

beforeEach(() => {
  state.branding = undefined;
  document.documentElement.style.removeProperty('--primary');
  document.documentElement.style.removeProperty('--sidebar-primary');
});

afterEach(() => cleanup());

describe('BrandingHead', () => {
  test('writes the primary colour as a CSS variable on :root', () => {
    state.branding = { appName: 'Acme', primaryColor: '#ff0000', logoUrl: null, faviconUrl: null };
    render(<BrandingHead />);
    expect(document.documentElement.style.getPropertyValue('--primary')).toBe('#ff0000');
    expect(document.documentElement.style.getPropertyValue('--sidebar-primary')).toBe('#ff0000');
  });

  test('renders a favicon link when a faviconUrl is set', () => {
    state.branding = {
      appName: 'Acme',
      primaryColor: null,
      logoUrl: null,
      faviconUrl: '/api/file-storage/files/fav/download',
    };
    render(<BrandingHead />);
    // React 19 hoists <link> into <head>, so query the whole document.
    const link = document.querySelector('link[rel="icon"]');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('href')).toBe('/api/file-storage/files/fav/download');
  });

  test('does not set the colour variable when none is configured', () => {
    state.branding = { appName: 'Acme', primaryColor: null, logoUrl: null, faviconUrl: null };
    render(<BrandingHead />);
    expect(document.documentElement.style.getPropertyValue('--primary')).toBe('');
  });
});
