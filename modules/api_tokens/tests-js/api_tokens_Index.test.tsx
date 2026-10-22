import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const state = vi.hoisted(() => ({ props: {} as ComponentProps<typeof Index> }));
const reload = vi.hoisted(() => vi.fn());

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { reload, visit: vi.fn(), get: vi.fn(), post: vi.fn() },
  usePage: () => ({ props: state.props }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import Index from '../api_tokens/pages/Index';
import { sent, stubFetch, token } from './fixtures';

const SECRET = 'smpy_pat_topsecretvalue';

function setProps(over: Partial<ComponentProps<typeof Index>> = {}) {
  state.props = {
    tokens: [token()],
    scopes: ['files.read', 'files.write'],
    max_lifetime_days: 365,
    expiry_presets: [7, 30, 90],
    csrf_token: 'csrf-abc',
    ...over,
  };
}

const f = keys.api_tokens.form;
const rv = keys.api_tokens.revoke;
const ra = keys.api_tokens.revoke_all;

async function createToken() {
  fireEvent.click(screen.getByRole('button', { name: f.new_token }));
  fireEvent.change(await screen.findByLabelText(f.name), { target: { value: 'deploy' } });
  fireEvent.click(screen.getByLabelText('files.read'));
  fireEvent.click(screen.getByRole('button', { name: f.submit }));
}

describe('api_tokens Index', () => {
  beforeEach(() => setProps());
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('lists the tokens by name and prefix, never a secret', () => {
    render(<Index {...state.props} />);
    expect(screen.getByText('ci-token')).toBeInTheDocument();
    expect(screen.getByText('smpy_ab12…')).toBeInTheDocument();
    expect(screen.getByText(keys.api_tokens.status.active)).toBeInTheDocument();
  });

  it('shows the empty state and disables Revoke all with no tokens', () => {
    setProps({ tokens: [] });
    render(<Index {...state.props} />);
    expect(screen.getByText(keys.api_tokens.list.empty_title)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: ra.button })).toBeDisabled();
  });

  it('disables New token when the caller holds no scopes', () => {
    setProps({ scopes: [] });
    render(<Index {...state.props} />);
    expect(screen.getByRole('button', { name: f.new_token })).toBeDisabled();
  });

  it('offers no Revoke action on revoked or expired rows', () => {
    setProps({
      tokens: [
        token({ id: 'r', name: 'old', revoked_at: '2026-02-01T00:00:00Z' }),
        token({ id: 'e', name: 'lapsed', expires_at: '2020-01-01T00:00:00Z' }),
      ],
    });
    render(<Index {...state.props} />);
    expect(screen.queryByRole('button', { name: keys.api_tokens.list.revoke })).toBeNull();
    expect(screen.getByRole('button', { name: ra.button })).toBeDisabled();
  });

  it('creates a token, posting JSON with the CSRF header, and reveals the secret once', async () => {
    const fetchMock = stubFetch(201, { token: SECRET, item: token({ id: 't2' }) });
    render(<Index {...state.props} />);
    await createToken();

    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    const request = await sent(fetchMock);
    expect(request.path).toBe('/api/api_tokens/tokens/');
    expect(request.method).toBe('POST');
    expect(request.headers.get('X-CSRF-Token')).toBe('csrf-abc');
    expect(request.body).toMatchObject({
      name: 'deploy',
      scopes: ['files.read'],
      expires_in_days: 30,
    });
    expect(reload).toHaveBeenCalledWith({ only: ['tokens'] });
  });

  it('removes the secret once dismissed and never renders it after a reload', async () => {
    stubFetch(201, { token: SECRET, item: token({ id: 't2' }) });
    const { rerender } = render(<Index {...state.props} />);
    await createToken();
    await screen.findByText(SECRET);

    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.created.done }));
    await waitFor(() => expect(screen.queryByText(SECRET)).toBeNull());

    // The reloaded `tokens` prop carries only the prefix.
    setProps({ tokens: [token(), token({ id: 't2', name: 'deploy', prefix: 'smpy_cd34' })] });
    rerender(<Index {...state.props} />);
    expect(screen.getByText('smpy_cd34…')).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(SECRET);
  });

  it('does not bring the secret back after navigating away and returning', async () => {
    stubFetch(201, { token: SECRET, item: token({ id: 't2' }) });
    const first = render(<Index {...state.props} />);
    await createToken();
    await screen.findByText(SECRET);
    first.unmount();

    render(<Index {...state.props} />);
    expect(document.body.textContent).not.toContain(SECRET);
    expect(screen.queryByText(keys.api_tokens.created.title)).toBeNull();
  });

  it('toasts the server detail and shows no secret when creation is refused', async () => {
    stubFetch(400, { detail: 'Name already in use' });
    render(<Index {...state.props} />);
    await createToken();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Name already in use'));
    expect(screen.queryByText(keys.api_tokens.created.title)).toBeNull();
    expect(reload).not.toHaveBeenCalled();
  });

  it('falls back to the generic toast when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    render(<Index {...state.props} />);
    await createToken();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(keys.api_tokens.toasts.failed));
  });

  it('asks for confirmation before revoking and calls nothing when cancelled', async () => {
    const fetchMock = stubFetch(200, {});
    render(<Index {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.list.revoke }));
    expect(await screen.findByText(rv.description)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: rv.cancel }));
    await waitFor(() => expect(screen.queryByText(rv.description)).toBeNull());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('revokes after confirmation, toasts and reloads the list', async () => {
    const fetchMock = stubFetch(200, token({ revoked_at: '2026-03-01T00:00:00Z' }));
    render(<Index {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: rv.confirm }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(keys.api_tokens.toasts.revoked));
    expect((await sent(fetchMock)).path).toBe('/api/api_tokens/tokens/t1/revoke');
    expect(reload).toHaveBeenCalledWith({ only: ['tokens'] });
  });

  it('toasts an error and does not reload when revoke fails', async () => {
    stubFetch(403, { detail: 'Not yours' });
    render(<Index {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: rv.confirm }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Not yours'));
    expect(toast.success).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
  });

  it('revoke-all confirms first, then posts to the bulk endpoint', async () => {
    const fetchMock = stubFetch(200, { revoked: 3 });
    render(<Index {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: ra.button }));
    expect(await screen.findByText(ra.description)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: ra.confirm }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect((await sent(fetchMock)).path).toBe('/api/api_tokens/tokens/revoke-all');
  });

  it('revoke-all does nothing when cancelled', async () => {
    const fetchMock = stubFetch(200, { revoked: 3 });
    render(<Index {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: ra.button }));
    fireEvent.click(await screen.findByRole('button', { name: ra.cancel }));
    await waitFor(() => expect(screen.queryByText(ra.description)).toBeNull());
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
