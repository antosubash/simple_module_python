import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

// Resolve keys to the key itself plus its count, so the assertions read as
// "which bucket, with what number" without depending on the English catalog.
vi.mock('@simple-module-py/i18n', () => ({
  useT: () => ({
    t: (key: string, opts?: { count?: number }) =>
      opts?.count === undefined ? key : `${key}:${opts.count}`,
  }),
}));

import { useRelativeTime } from './use-relative-time';

function Probe({ iso }: { iso: string | null | undefined }) {
  const { ago, until } = useRelativeTime();
  return (
    <>
      <span data-testid="ago">{ago(iso)}</span>
      <span data-testid="until">{until(iso)}</span>
    </>
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe('useRelativeTime', () => {
  test('describes a past timestamp as an age and a future one as a countdown', () => {
    vi.setSystemTime(new Date('2026-09-03T12:00:00Z'));
    render(<Probe iso="2026-09-03T09:00:00Z" />);
    expect(screen.getByTestId('ago')).toHaveTextContent('ui.relative_time.hours_ago:3');
    expect(screen.getByTestId('until')).toHaveTextContent('ui.relative_time.expired');
  });

  test('counts forward to a future timestamp', () => {
    vi.setSystemTime(new Date('2026-09-03T12:00:00Z'));
    render(<Probe iso="2026-09-05T12:00:00Z" />);
    expect(screen.getByTestId('until')).toHaveTextContent('ui.relative_time.in_days:2');
  });

  test('falls back to "unknown" for input it cannot read', () => {
    render(<Probe iso="not a date" />);
    expect(screen.getByTestId('ago')).toHaveTextContent('ui.relative_time.unknown');
    expect(screen.getByTestId('until')).toHaveTextContent('ui.relative_time.unknown');
  });

  test('falls back to "unknown" for a missing timestamp', () => {
    render(<Probe iso={null} />);
    expect(screen.getByTestId('ago')).toHaveTextContent('ui.relative_time.unknown');
    expect(screen.getByTestId('until')).toHaveTextContent('ui.relative_time.unknown');
  });
});
