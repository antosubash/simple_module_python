import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

// The install's locale list is what this control branches on, so the mocked
// shared prop is per-test rather than fixed at module scope.
const i18nProps = vi.hoisted(() => ({
  current: { locale: 'en', supportedLocales: ['en', 'es'], messages: {} } as {
    locale: string;
    supportedLocales: string[];
    messages: Record<string, string>;
  },
}));

vi.mock('@inertiajs/react', () => ({
  usePage: () => ({ props: { i18n: i18nProps.current } }),
}));

vi.mock('@simple-module-py/i18n', () => {
  const labels: Record<string, string> = {
    'ui.switcher.label': 'Change language',
    'ui.switcher.single_locale': 'Only {locale} is enabled',
  };
  return {
    useT: () => ({
      t: (key: string, vars?: Record<string, string>) =>
        Object.entries(vars ?? {}).reduce(
          (text, [name, value]) => text.replace(`{${name}}`, value),
          labels[key] ?? key,
        ),
    }),
    keys: {
      ui: {
        switcher: { label: 'ui.switcher.label', single_locale: 'ui.switcher.single_locale' },
      },
    },
  };
});

import { LocaleSwitcher, useHasMultipleLocales } from './LocaleSwitcher';

/** Stands in for the drawer footer, which renders its strip only when true. */
function LocaleGate() {
  return <span data-testid="gate">{String(useHasMultipleLocales())}</span>;
}

describe('LocaleSwitcher', () => {
  beforeEach(() => {
    i18nProps.current = { locale: 'en', supportedLocales: ['en', 'es'], messages: {} };
  });

  test('renders when multiple locales supported', () => {
    render(<LocaleSwitcher />);
    expect(screen.getByRole('button', { name: /change language/i })).toBeInTheDocument();
  });

  test('shows the active locale as a text pill', () => {
    render(<LocaleSwitcher />);
    expect(screen.getByRole('button', { name: /change language/i })).toHaveTextContent('EN');
  });

  test('form targets /i18n/set-locale', () => {
    const { container } = render(<LocaleSwitcher />);
    const form = container.querySelector('form');
    expect(form?.getAttribute('action')).toBe('/i18n/set-locale');
    expect(form?.getAttribute('method')?.toLowerCase()).toBe('post');
  });

  test('renders a static pill when only one locale is enabled', () => {
    i18nProps.current = { locale: 'en', supportedLocales: ['en'], messages: {} };
    render(<LocaleSwitcher />);
    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByTitle('Only EN is enabled')).toHaveTextContent('EN');
  });
});

describe('useHasMultipleLocales', () => {
  test('is true when the install offers a choice', () => {
    i18nProps.current = { locale: 'en', supportedLocales: ['en', 'es'], messages: {} };
    render(<LocaleGate />);
    expect(screen.getByTestId('gate')).toHaveTextContent('true');
  });

  test('is false on a single-locale install, so the drawer omits the strip', () => {
    i18nProps.current = { locale: 'en', supportedLocales: ['en'], messages: {} };
    render(<LocaleGate />);
    expect(screen.getByTestId('gate')).toHaveTextContent('false');
  });
});
