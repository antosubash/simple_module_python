import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

  it('clears the displayed result when the package changes', async () => {
    stub(200, { checks: [{ name: 'a.b', status: 'healthy', detail: 'users connected' }] });
    const { rerender } = render(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
    click();
    expect(await screen.findByText('users connected')).toBeVisible();
    rerender(<TestConnectionButton pkg="mail" checks={['a.b', 'c.d']} />);
    expect(screen.queryByText('users connected')).not.toBeInTheDocument();
  });

  it('ignores a pending result after switching packages, including switching back', async () => {
    let finish!: (response: Response) => void;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    const { rerender } = render(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
    click();
    rerender(<TestConnectionButton pkg="mail" checks={['a.b', 'c.d']} />);
    expect(screen.getByRole('button')).toBeEnabled();
    rerender(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
    await act(async () =>
      finish(
        new Response(
          JSON.stringify({
            checks: [{ name: 'a.b', status: 'healthy', detail: 'stale result' }],
          }),
          { status: 200 },
        ),
      ),
    );
    expect(screen.queryByText('stale result')).not.toBeInTheDocument();
    expect(window.sessionStorage.getItem('sm.settings.last-test.users')).toBeNull();
  });

  it.each([null, {}, { checks: [] }, { checks: 'invalid' }])(
    'does not record success for an invalid check response: %j',
    async (body) => {
      stub(200, body);
      render(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
      click();
      expect(await screen.findByText(keys.settings.modules.test_failed)).toBeVisible();
      expect(
        JSON.parse(window.sessionStorage.getItem('sm.settings.last-test.users') ?? '{}').ok,
      ).toBe(false);
    },
  );

  it('does not record success when the response body cannot be read', async () => {
    const response = new Response('{}', { status: 200 });
    vi.spyOn(response, 'text').mockRejectedValue(new TypeError('stream interrupted'));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response));
    render(<TestConnectionButton pkg="users" checks={['a.b', 'c.d']} />);
    click();
    expect(await screen.findByText(keys.settings.modules.test_failed)).toBeVisible();
    expect(
      JSON.parse(window.sessionStorage.getItem('sm.settings.last-test.users') ?? '{}').ok,
    ).toBe(false);
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
