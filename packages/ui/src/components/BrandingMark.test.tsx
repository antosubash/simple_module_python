import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import { BrandingMark } from './BrandingMark';

describe('BrandingMark', () => {
  test('renders the app name as the wordmark', () => {
    render(<BrandingMark appName="Acme Corp" accentColor="bg-blue-500" />);
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  test('renders the custom logo when a logoUrl is provided', () => {
    render(
      <BrandingMark
        appName="Acme"
        logoUrl="/api/file-storage/files/abc/download"
        accentColor="bg-blue-500"
      />,
    );
    const img = screen.getByRole('img', { name: 'Acme' });
    expect(img).toHaveAttribute('src', '/api/file-storage/files/abc/download');
  });

  test('falls back to the app initial badge when there is no logo', () => {
    render(<BrandingMark appName="Zephyr" accentColor="bg-blue-500" />);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByText('Z')).toBeInTheDocument();
  });
});
