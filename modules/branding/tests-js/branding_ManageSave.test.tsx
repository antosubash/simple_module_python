import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

const reload = vi.hoisted(() => vi.fn());
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children }: { children: React.ReactNode }) => <a href="/x">{children}</a>,
  router: { reload },
  usePage: () => ({ props: {} }),
}));
vi.mock('@simple-module-py/ui/layouts/AdminLayout', () => ({ AdminLayout: () => null }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import Manage from '../branding/pages/Manage';

function props() {
  return {
    auth: { permissions: ['branding.manage'] },
    branding: { appName: 'Acme' },
  } as unknown as ComponentProps<typeof Manage>;
}

function stub(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('branding Manage publish', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('PUTs the form as JSON, toasts and reloads', async () => {
    const fetchMock = stub(200, {});
    render(<Manage {...props()} />);
    fireEvent.change(screen.getByLabelText(keys.branding.manage.app_name_label), {
      target: { value: 'Globex' },
    });
    fireEvent.click(screen.getByRole('button', { name: keys.branding.manage.publish }));

    await waitFor(() => expect(reload).toHaveBeenCalled());
    const [req] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(req.method).toBe('PUT');
    expect(new URL(req.url).pathname).toBe('/api/branding/');
    expect((await req.json()).app_name).toBe('Globex');
    expect(toast.success).toHaveBeenCalledWith(keys.branding.manage.saved_toast);
  });

  it('shows the server detail after the translated prefix on failure', async () => {
    stub(400, { detail: 'bad colour' });
    render(<Manage {...props()} />);
    fireEvent.change(screen.getByLabelText(keys.branding.manage.app_name_label), {
      target: { value: 'Globex' },
    });
    fireEvent.click(screen.getByRole('button', { name: keys.branding.manage.publish }));

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error).toHaveBeenCalledWith(`${keys.branding.manage.error_toast}: bad colour`);
    expect(reload).not.toHaveBeenCalled();
  });
});
