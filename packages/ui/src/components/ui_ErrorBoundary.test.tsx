import { render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { reportClientError } from '../lib/client-errors';
import { ErrorBoundary } from './ErrorBoundary';

vi.mock('../lib/client-errors', () => ({ reportClientError: vi.fn() }));
afterEach(() => vi.restoreAllMocks());

const error = new Error('broken page');

function Broken(): never {
  throw error;
}

test('reports render errors through the shared hook and preserves the caller callback', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  const onError = vi.fn();
  render(
    <ErrorBoundary onError={onError} fallback={() => <p>Recovered</p>}>
      <Broken />
    </ErrorBoundary>,
  );
  expect(screen.getByText('Recovered')).toBeTruthy();
  expect(reportClientError).toHaveBeenCalledWith(
    error,
    expect.objectContaining({ componentStack: expect.any(String) }),
  );
  expect(onError).toHaveBeenCalledWith(
    error,
    expect.objectContaining({ componentStack: expect.any(String) }),
  );
});
