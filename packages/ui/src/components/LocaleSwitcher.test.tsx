import { render, screen } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';

// Mock @inertiajs/react's usePage before importing the component under test.
vi.mock('@inertiajs/react', () => ({
  usePage: () => ({
    props: {
      i18n: {
        locale: 'en',
        supportedLocales: ['en', 'es'],
        messages: {},
      },
    },
  }),
}));

import { LocaleSwitcher } from './LocaleSwitcher';

describe('LocaleSwitcher', () => {
  test('renders when multiple locales supported', () => {
    render(<LocaleSwitcher />);
    expect(screen.getByRole('button', { name: /change language/i })).toBeInTheDocument();
  });

  test('form targets /i18n/set-locale', () => {
    const { container } = render(<LocaleSwitcher />);
    const form = container.querySelector('form');
    expect(form?.getAttribute('action')).toBe('/i18n/set-locale');
    expect(form?.getAttribute('method')?.toLowerCase()).toBe('post');
  });
});
