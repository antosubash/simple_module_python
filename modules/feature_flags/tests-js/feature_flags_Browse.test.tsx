import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const state = vi.hoisted(() => ({ props: {} as Record<string, unknown> }));
const post = vi.hoisted(() => vi.fn());
const visit = vi.hoisted(() => vi.fn());

vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { post, visit },
  usePage: () => ({ props: state.props }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import Browse from '../feature_flags/pages/Browse';
import type { FeatureFlag } from '../feature_flags/pages/types';

const FLAGS: FeatureFlag[] = [
  {
    name: 'beta_search',
    description: 'New search',
    default_enabled: false,
    enabled: false,
    overridden: false,
    system_enabled: null,
  },
  {
    name: 'dark_mode',
    description: 'Dark theme',
    default_enabled: false,
    enabled: true,
    overridden: true,
    system_enabled: null,
  },
];

function setProps(over: Record<string, unknown> = {}, permissions = ['feature_flags.manage']) {
  state.props = {
    flags: FLAGS,
    tenant_id: null,
    tenants: ['acme'],
    audit_log_url: null,
    auth: { permissions },
    ...over,
  };
}

type PostOptions = { onSuccess: () => void; onError: () => void; preserveScroll: boolean };

const confirm = keys.feature_flags.confirm;
const table = keys.feature_flags.table;
const browse = keys.feature_flags.browse;

describe('feature_flags Browse', () => {
  beforeEach(() => setProps());
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders every flag with its description and override badge', () => {
    render(<Browse />);
    expect(screen.getByText('beta_search')).toBeInTheDocument();
    expect(screen.getByText('dark_mode')).toBeInTheDocument();
    expect(screen.getByText('Dark theme')).toBeInTheDocument();
    expect(screen.getAllByText(table.overridden)).toHaveLength(1);
  });

  it('shows the empty state when no module registers flags', () => {
    setProps({ flags: [] });
    render(<Browse />);
    expect(screen.getByText(browse.empty_title)).toBeInTheDocument();
  });

  it('links to the audit history only when an audit log is installed', () => {
    const { unmount } = render(<Browse />);
    expect(screen.queryByText(browse.view_history)).toBeNull();
    unmount();
    setProps({ audit_log_url: '/admin/audit?x=1' });
    render(<Browse />);
    expect(screen.getByText(browse.view_history)).toHaveAttribute('href', '/admin/audit?x=1');
  });

  it('makes the switches read-only without the manage permission', () => {
    setProps({}, []);
    render(<Browse />);
    expect(screen.getByRole('switch', { name: 'beta_search' })).toBeDisabled();
    expect(screen.queryByText(table.clear_override)).toBeNull();
  });

  it('stages a toggle behind a confirm and writes nothing until confirmed', async () => {
    render(<Browse />);
    fireEvent.click(screen.getByRole('switch', { name: 'beta_search' }));
    expect(await screen.findByText(confirm.scope_system)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('cancelling the confirm leaves the flag and the server untouched', async () => {
    render(<Browse />);
    fireEvent.click(screen.getByRole('switch', { name: 'beta_search' }));
    fireEvent.click(await screen.findByRole('button', { name: confirm.cancel }));
    await waitFor(() => expect(screen.queryByText(confirm.scope_system)).toBeNull());
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole('switch', { name: 'beta_search' })).not.toBeChecked();
  });

  it('enables a flag on confirm, posting enabled=true to the system scope', async () => {
    render(<Browse />);
    fireEvent.click(screen.getByRole('switch', { name: 'beta_search' }));
    fireEvent.click(await screen.findByRole('button', { name: confirm.enable_action }));

    expect(post).toHaveBeenCalledTimes(1);
    const [url, data, options] = post.mock.calls[0] as [string, unknown, PostOptions];
    expect(url).toBe('/admin/feature-flags/beta_search/toggle');
    expect(data).toEqual({ enabled: true });
    expect(options.preserveScroll).toBe(true);
    options.onSuccess();
    expect(toast.success).toHaveBeenCalledWith(keys.feature_flags.toasts.enabled);
  });

  it('disables a flag on confirm and toasts a failure from the server', async () => {
    render(<Browse />);
    fireEvent.click(screen.getByRole('switch', { name: 'dark_mode' }));
    fireEvent.click(await screen.findByRole('button', { name: confirm.disable_action }));

    const [, data, options] = post.mock.calls[0] as [string, unknown, PostOptions];
    expect(data).toEqual({ enabled: false });
    options.onSuccess();
    expect(toast.success).toHaveBeenCalledWith(keys.feature_flags.toasts.disabled);
    options.onError();
    expect(toast.error).toHaveBeenCalledWith(keys.feature_flags.toasts.toggle_failed);
  });

  it('scopes the toggle URL and the confirm text to the viewed tenant', async () => {
    setProps({ tenant_id: 'acme corp' });
    render(<Browse />);
    fireEvent.click(screen.getByRole('switch', { name: 'beta_search' }));
    expect(await screen.findByText(confirm.scope_tenant)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: confirm.enable_action }));
    expect(post.mock.calls[0][0]).toBe(
      '/admin/feature-flags/beta_search/toggle?tenant_id=acme%20corp',
    );
  });

  it('clears an override without a confirm and reports the result', () => {
    render(<Browse />);
    fireEvent.click(screen.getAllByText(table.clear_override)[0]);
    const [url, data, options] = post.mock.calls[0] as [string, unknown, PostOptions];
    expect(url).toBe('/admin/feature-flags/dark_mode/clear');
    expect(data).toEqual({});
    options.onSuccess();
    expect(toast.success).toHaveBeenCalledWith(keys.feature_flags.toasts.cleared);
    options.onError();
    expect(toast.error).toHaveBeenCalledWith(keys.feature_flags.toasts.toggle_failed);
  });

  it('explains which value a non-overridden flag follows', () => {
    render(<Browse />);
    expect(screen.getAllByText(table.following_default).length).toBeGreaterThan(0);
    cleanup();
    setProps({ tenant_id: 'acme' });
    render(<Browse />);
    expect(screen.getAllByText(table.following_system).length).toBeGreaterThan(0);
  });

  it('switches scope by visiting the tenant URL, or the system URL', () => {
    render(<Browse />);
    fireEvent.click(screen.getByRole('radio', { name: 'acme' }));
    expect(visit).toHaveBeenCalledWith('/admin/feature-flags/?tenant_id=acme');
    cleanup();
    setProps({ tenant_id: 'acme' });
    render(<Browse />);
    fireEvent.click(screen.getByRole('radio', { name: browse.scope_system }));
    expect(visit).toHaveBeenLastCalledWith('/admin/feature-flags/');
  });

  it('lets an operator name a tenant with no overrides yet', () => {
    render(<Browse />);
    fireEvent.click(screen.getByRole('radio', { name: browse.scope_custom }));
    const go = screen.getByRole('button', { name: browse.go });
    expect(go).toBeDisabled();
    fireEvent.change(screen.getByLabelText(browse.tenant_id_label), {
      target: { value: '  new-co ' },
    });
    fireEvent.click(go);
    expect(visit).toHaveBeenCalledWith('/admin/feature-flags/?tenant_id=new-co');
  });
});
