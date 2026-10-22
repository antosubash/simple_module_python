import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const state = vi.hoisted(() => ({ props: {} as ComponentProps<typeof Admin> }));
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
import Admin from '../api_tokens/pages/Admin';
import { sent, stubFetch, token } from './fixtures';

const SECRET = 'smpy_svc_adminsecret';

const SERVICE = token({
  id: 's1',
  kind: 'service',
  name: 'ingest-bot',
  prefix: 'smpy_zz99',
  roles: ['uploader'],
  owner_user_id: null,
  owner_email: null,
  tenant_id: 'acme',
});

function setProps(over: Partial<ComponentProps<typeof Admin>> = {}) {
  state.props = {
    tokens: [SERVICE],
    scopes: ['files.read'],
    roles: ['uploader', 'reader'],
    tenant_required: false,
    max_lifetime_days: 365,
    expiry_presets: [7, 30],
    csrf_token: 'csrf-xyz',
    ...over,
  };
}

describe('api_tokens Admin', () => {
  beforeEach(() => setProps());
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('lists every token with its kind and role-based owner', () => {
    render(<Admin {...state.props} />);
    expect(screen.getByText('ingest-bot')).toBeInTheDocument();
    expect(screen.getByText(keys.api_tokens.kind.service)).toBeInTheDocument();
    expect(screen.getByText('uploader')).toBeInTheDocument();
  });

  it('shows the empty state when there are no tokens', () => {
    setProps({ tokens: [] });
    render(<Admin {...state.props} />);
    expect(screen.getByText(keys.api_tokens.list.empty_title)).toBeInTheDocument();
  });

  it('replaces the table with a banner and disables creation without a tenant', () => {
    setProps({ tenant_required: true });
    render(<Admin {...state.props} />);
    expect(screen.getByText(keys.api_tokens.admin.tenant_required)).toBeInTheDocument();
    expect(screen.queryByText('ingest-bot')).toBeNull();
    expect(
      screen.getByRole('button', { name: keys.api_tokens.admin.new_service_key }),
    ).toBeDisabled();
  });

  it('creates a service key with roles and reveals its secret', async () => {
    const fetchMock = stubFetch(201, { token: SECRET, item: SERVICE });
    render(<Admin {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.admin.new_service_key }));
    fireEvent.change(await screen.findByLabelText(keys.api_tokens.form.name), {
      target: { value: 'robot' },
    });
    fireEvent.click(screen.getByLabelText('files.read'));
    fireEvent.click(screen.getByLabelText('reader'));
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.form.submit }));

    expect(await screen.findByText(SECRET)).toBeInTheDocument();
    const request = await sent(fetchMock);
    expect(request.path).toBe('/api/api_tokens/admin/service-keys');
    expect(request.headers.get('X-CSRF-Token')).toBe('csrf-xyz');
    expect(request.body).toMatchObject({ name: 'robot', roles: ['reader'] });
  });

  it('confirms before revoking via the admin endpoint, and not when cancelled', async () => {
    const fetchMock = stubFetch(200, SERVICE);
    render(<Admin {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: keys.api_tokens.revoke.cancel }));
    await waitFor(() => expect(screen.queryByText(keys.api_tokens.revoke.description)).toBeNull());
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: keys.api_tokens.revoke.confirm }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect((await sent(fetchMock)).path).toBe('/api/api_tokens/admin/tokens/s1/revoke');
  });

  it('toasts the generic error when revoke fails without a detail', async () => {
    stubFetch(500, {});
    render(<Admin {...state.props} />);
    fireEvent.click(screen.getByRole('button', { name: keys.api_tokens.list.revoke }));
    fireEvent.click(await screen.findByRole('button', { name: keys.api_tokens.revoke.confirm }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(keys.api_tokens.toasts.failed));
  });
});
