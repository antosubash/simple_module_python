import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

import { TestConnectionButton } from '../settings/pages/components/TestConnectionButton';

function stub(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const click = () =>
  fireEvent.click(
    screen.getByRole('button', { name: keys.settings.modules.test_connection_generic }),
  );

describe('TestConnectionButton', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.sessionStorage.clear();
  });

  it('POSTs to the view route and shows each check detail', async () => {
    const fetchMock = stub(200, {
      checks: [{ name: 'users.mailer', status: 'unhealthy', detail: 'connection refused' }],
    });
    render(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
    click();
    expect(await screen.findByText('connection refused')).toBeInTheDocument();
    const [req] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(req.method).toBe('POST');
    expect(new URL(req.url).pathname).toBe('/admin/settings/test-connection/users');
  });

  it('shows a translated line when the call itself fails', async () => {
    stub(500, null);
    render(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
    click();
    await waitFor(() =>
      expect(screen.getByText(keys.settings.modules.test_failed)).toBeInTheDocument(),
    );
  });
});
