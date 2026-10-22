import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

import { ConnectionList } from '../simple_module_hosting/setup_wizard/components/ConnectionList';
import { StepForm } from '../simple_module_hosting/setup_wizard/components/StepForm';

function stub(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const action = {
  submitLabel: 'Create admin',
  fields: [
    {
      name: 'email',
      label: 'Email',
      type: 'text',
      required: false,
      autocomplete: '',
      minLength: null,
    },
    {
      name: 'note',
      label: 'Note',
      type: 'text',
      required: false,
      autocomplete: '',
      minLength: null,
    },
  ],
};

describe('StepForm', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('POSTs the fields as JSON with the page-prop CSRF token', async () => {
    const fetchMock = stub(200, {});
    render(<StepForm stepId="admin user" action={action} csrfToken="page-token" />);
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.co' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Create admin' }).closest('form')!);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [req] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(req.method).toBe('POST');
    expect(new URL(req.url).pathname).toBe('/setup/steps/admin%20user');
    expect(req.headers.get('X-CSRF-Token')).toBe('page-token');
    expect(req.headers.get('Accept')).toBe('application/json');
    expect(await req.json()).toEqual({ email: 'a@b.co', note: null });
  });

  it('joins the messages of a 422 detail list', async () => {
    stub(422, { detail: [{ msg: 'too short' }, { msg: 'bad address' }] });
    render(<StepForm stepId="s" action={action} csrfToken="t" />);
    fireEvent.submit(screen.getByRole('button', { name: 'Create admin' }).closest('form')!);
    expect(await screen.findByText('too short; bad address')).toBeInTheDocument();
  });

  it('falls back to a translated line when the body has no detail', async () => {
    stub(500, null);
    render(<StepForm stepId="s" action={action} csrfToken="t" />);
    fireEvent.submit(screen.getByRole('button', { name: 'Create admin' }).closest('form')!);
    expect(await screen.findByText(keys.hosting.setup.request_failed)).toBeInTheDocument();
  });
});

describe('ConnectionList', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('retests with the page-prop token and replaces the list', async () => {
    const fetchMock = stub(200, {
      checks: [{ name: 'redis', status: 'healthy', detail: 'ok' }],
    });
    render(<ConnectionList initial={[]} csrfToken="page-token" />);
    fireEvent.click(screen.getByRole('button', { name: keys.hosting.setup.connections.retest }));
    expect(await screen.findByText('redis')).toBeInTheDocument();
    const [req] = fetchMock.mock.calls[0] as unknown as [Request];
    expect(new URL(req.url).pathname).toBe('/setup/test-connections');
    expect(req.headers.get('X-CSRF-Token')).toBe('page-token');
  });

  it('shows an error line when setup finished in another tab (404)', async () => {
    stub(404, null);
    render(<ConnectionList initial={[]} csrfToken="t" />);
    fireEvent.click(screen.getByRole('button', { name: keys.hosting.setup.connections.retest }));
    expect(await screen.findByText(keys.hosting.setup.request_failed)).toBeInTheDocument();
  });
});
