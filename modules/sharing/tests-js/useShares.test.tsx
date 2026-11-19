import { configureI18n, keys } from '@simple-module-py/i18n';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useShares } from '../sharing/ui/hooks/useShares';

configureI18n({ locale: 'en', messages: {} });
const candidate = { id: 'friend', display_name: 'Friend', email: 'friend@test' };
const share = {
  id: 'share',
  resource_type: 'notes.note',
  resource_id: 'note',
  subject_type: 'user',
  subject_id: 'friend',
  subject_label: 'Friend',
  role: 'view',
  granted_by: 'owner',
  granted_by_label: 'Owner',
  expires_at: null,
  expired: false,
  created_at: null,
};
let requests: Request[];
let fail: boolean;
beforeEach(() => {
  requests = [];
  fail = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      requests.push(request);
      if (fail) return Response.json({ detail: 'Failure' }, { status: 403 });
      if (request.method === 'DELETE') return new Response(null, { status: 204 });
      if (request.method === 'POST') return Response.json(share, { status: 201 });
      return Response.json(request.url.includes('/candidates') ? [candidate] : []);
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it('waits for open, searches trimmed terms, adds and removes with typed requests', async () => {
  const { result, rerender } = renderHook(({ open }) => useShares('notes.note', 'note', open), {
    initialProps: { open: false },
  });
  expect(requests).toHaveLength(0);
  rerender({ open: true });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(new URL(requests[0].url).searchParams.get('resource_id')).toBe('note');
  act(() => result.current.setQuery('ab'));
  expect(result.current.tooShort).toBe(true);
  vi.useFakeTimers();
  act(() => result.current.setQuery('  friend  '));
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(result.current.candidates).toEqual([candidate]);
  const candidateRequest = requests.find((r) => r.url.includes('/candidates'));
  if (!candidateRequest) throw new Error('Missing candidates request');
  const search = new URL(candidateRequest.url);
  expect(search.pathname).toBe('/api/sharing/candidates');
  expect(search.searchParams.get('q')).toBe('friend');
  expect(search.searchParams.get('resource_type')).toBe('notes.note');
  await act(() => result.current.grant(candidate, 'view'));
  expect(result.current.shares).toEqual([share]);
  expect(result.current.candidates).toEqual([]);
  expect(await requests.find((r) => r.method === 'POST')?.json()).toEqual({
    resource_type: 'notes.note',
    resource_id: 'note',
    subject_id: 'friend',
    subject_type: 'user',
    role: 'view',
  });
  await act(() => result.current.revoke(share));
  expect(result.current.shares).toEqual([]);
  expect(requests.at(-1)?.url).toContain('/api/sharing/shares/share');
});

it('shows translated failures without claiming a grant succeeded', async () => {
  const { result } = renderHook(() => useShares('notes.note', 'note', true));
  await waitFor(() => expect(result.current.loading).toBe(false));
  fail = true;
  await act(() => result.current.grant(candidate, 'edit'));
  expect(result.current.error).toBe(keys.sharing.dialog.failed);
  expect(result.current.shares).toEqual([]);
});

it('does not keep candidates from the previous query or a closed dialog', async () => {
  const { result, rerender } = renderHook(({ open }) => useShares('notes.note', 'note', open), {
    initialProps: { open: true },
  });
  await waitFor(() => expect(result.current.loading).toBe(false));
  vi.useFakeTimers();
  act(() => result.current.setQuery('friend'));
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(result.current.candidates).toEqual([candidate]);
  act(() => result.current.setQuery('other'));
  expect(result.current.candidates).toEqual([]);
  rerender({ open: false });
  await act(() => vi.advanceTimersByTimeAsync(250));
  expect(requests.filter((r) => r.url.includes('/candidates'))).toHaveLength(1);
});

it('blocks duplicate grants and ignores a grant response after the resource changes', async () => {
  let finish = (_response: Response) => {};
  const writing = new Promise<Response>((resolve) => {
    finish = resolve;
  });
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request) => {
      requests.push(request);
      return request.method === 'POST' ? writing : Promise.resolve(Response.json([]));
    }),
  );
  const { result, rerender } = renderHook(({ id }) => useShares('notes.note', id, true), {
    initialProps: { id: 'old' },
  });
  await waitFor(() => expect(result.current.loading).toBe(false));
  let mutation: Promise<void>;
  act(() => {
    mutation = result.current.grant(candidate, 'view');
    void result.current.grant(candidate, 'view');
  });
  await waitFor(() =>
    expect(requests.filter((request) => request.method === 'POST')).toHaveLength(1),
  );
  rerender({ id: 'new' });
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => {
    finish(Response.json(share, { status: 201 }));
    await mutation;
  });
  expect(result.current.shares).toEqual([]);
  expect(result.current.pending).toBe(false);
});

it('refreshes after a delayed mutation settles across closing and reopening', async () => {
  let finish!: () => void;
  let held = false;
  const writing = new Promise<void>((resolve) => {
    finish = resolve;
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      if (request.method === 'POST') {
        await writing;
        held = true;
        return Response.json(share, { status: 201 });
      }
      return Response.json(held ? [share] : []);
    }),
  );
  const { result, rerender } = renderHook(({ open }) => useShares('notes.note', 'note', open), {
    initialProps: { open: true },
  });
  await waitFor(() => expect(result.current.loading).toBe(false));
  let mutation!: Promise<void>;
  act(() => {
    mutation = result.current.grant(candidate, 'view');
  });
  rerender({ open: false });
  rerender({ open: true });
  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.pending).toBe(true);
  await act(async () => {
    finish();
    await mutation;
  });
  await waitFor(() => expect(result.current.shares).toEqual([share]));
  expect(result.current.pending).toBe(false);
});
