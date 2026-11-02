/**
 * Tenants calls go through the typed client (#504): the path is filled from
 * the generated route, the session's CSRF token rides along, and a failure's
 * `{detail}` code (plus `limit` for plan_limit) maps to translated copy.
 */
import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { setCsrfToken } from '@simple-module-py/ui/lib/api';
import { failure } from '@simple-module-py/ui/lib/api-result';
import { cleanup, render, renderHook, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { MembershipList } from '../tenants/components/MembershipList';
import { useTenantErrors } from '../tenants/hooks/useTenantErrors';

configureI18n({
  locale: 'en',
  messages: {
    'tenants.index.switch_button': 'Switch',
    'tenants.index.toast_switch_failed': 'Could not switch',
    'tenants.errors.generic': 'Something went wrong',
    'tenants.errors.slug_taken': 'Slug taken',
    'tenants.errors.validation_failed': 'Check the form',
    'tenants.errors.plan_limit': 'Seat limit reached ({limit})',
  },
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  setCsrfToken(null);
});

describe('useTenantErrors.describe', () => {
  const { describe: text } = renderHook(() => useTenantErrors()).result.current;

  test('maps codes, validation and plan limits', () => {
    expect(text(failure(409, { detail: 'slug_taken' }))).toBe('Slug taken');
    expect(text(failure(422, { detail: [] }))).toBe('Check the form');
    expect(text(failure(402, { detail: 'plan_limit', limit: 5 }))).toBe('Seat limit reached (5)');
    expect(text(failure(500, '<html>'))).toBe('Something went wrong');
  });

  test('uses the caller’s offline copy when the request never left', () => {
    expect(text(failure(0, null), 'Could not switch')).toBe('Could not switch');
    expect(text(failure(0, null))).toBe('Something went wrong');
  });
});

test('switching posts to the generated route with the CSRF token', async () => {
  setCsrfToken('tok');
  const fetchMock = vi
    .spyOn(globalThis, 'fetch')
    .mockResolvedValue(new Response('{}', { status: 200 }));
  const onSwitched = vi.fn();
  render(
    <MembershipList
      memberships={[
        {
          id: 'abc',
          slug: 'acme',
          name: 'Acme',
          status: 'active',
          role: 'member',
          created_at: null,
        },
      ]}
      activeId={null}
      onSwitched={onSwitched}
    />,
  );
  await userEvent.click(screen.getByRole('button', { name: 'Switch' }));

  const request = fetchMock.mock.calls[0][0] as Request;
  expect(new URL(request.url).pathname).toBe('/api/tenants/abc/switch');
  expect(request.method).toBe('POST');
  expect(request.headers.get('X-CSRF-Token')).toBe('tok');
  expect(onSwitched).toHaveBeenCalledOnce();
});
