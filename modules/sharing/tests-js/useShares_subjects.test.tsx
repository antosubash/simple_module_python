import { configureI18n } from '@simple-module-py/i18n';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useShares } from '../sharing/ui/hooks/useShares';

configureI18n({ locale: 'en', messages: {} });
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it('searches by type and grants a role whose id also belongs to a user', async () => {
  const requests: Request[] = [];
  const role = {
    id: 'member',
    subject_type: 'tenant_role',
    display_name: 'tenant:member',
    email: '',
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      requests.push(request);
      if (request.url.includes('/subject-types'))
        return Response.json([
          { subject_type: 'user', label_key: 'sharing.subjects.user' },
          { subject_type: 'tenant_role', label_key: 'sharing.subjects.tenant_role' },
        ]);
      if (request.url.includes('/candidates')) return Response.json([role]);
      if (request.method === 'POST')
        return Response.json({
          id: 'role-share',
          subject_id: 'member',
          subject_type: 'tenant_role',
        });
      return Response.json([{ id: 'user-share', subject_id: 'member', subject_type: 'user' }]);
    }),
  );
  const { result } = renderHook(() => useShares('notes.note', 'one'));
  await waitFor(() => expect(result.current.subjectTypes).toHaveLength(2));
  vi.useFakeTimers();
  act(() => {
    result.current.setSubjectType('tenant_role');
    result.current.setQuery('member');
  });
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(result.current.candidates).toEqual([role]);
  const search = requests.find((r) => r.url.includes('/candidates'));
  if (!search) throw new Error('Missing search');
  expect(new URL(search.url).searchParams.get('subject_type')).toBe('tenant_role');
  await act(() => result.current.grant(role, 'view'));
  expect(await requests.find((r) => r.method === 'POST')?.json()).toMatchObject({
    subject_type: 'tenant_role',
    subject_id: 'member',
  });
  expect(result.current.shares).toHaveLength(2);
  act(() => result.current.setSubjectType('user'));
  expect(result.current.candidates).toEqual([]);
});
