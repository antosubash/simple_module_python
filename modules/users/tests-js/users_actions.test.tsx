import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const visit = vi.hoisted(() => vi.fn());
const reload = vi.hoisted(() => vi.fn());
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  Link: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  router: { visit, reload },
  usePage: () => ({ props: {} }),
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import ForgotPassword from '../users/pages/ForgotPassword';
import AddPeople from '../users/pages/Users/AddPeople';
import { json, sent, stubFetch } from './users_fixtures';

configureI18n({ locale: 'en', messages: {} });

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('users ForgotPassword', () => {
  it('posts the address as JSON and shows the confirmation', async () => {
    const mock = stubFetch(() => json(202, null));
    render(<ForgotPassword reset_link_lifetime_minutes={30} mailer_delivers />);
    fireEvent.change(document.getElementById('email') as HTMLElement, {
      target: { value: 'a@example.com' },
    });
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    await waitFor(() => expect(document.getElementById('email')).toBeNull());
    const call = await sent(mock);
    expect(call.path).toBe('/api/users/auth/forgot-password');
    expect(JSON.parse(call.text)).toEqual({ email: 'a@example.com' });
  });
});

describe('users AddPeople', () => {
  const props = { roles: [], mailer_delivers: true, mailer_name: 'smtp', invite_expiry_days: 7 };

  function create() {
    window.history.pushState({}, '', '/admin/users/add?mode=create');
    render(<AddPeople {...props} />);
    fireEvent.change(document.querySelector('input[type="email"]') as HTMLElement, {
      target: { value: 'new@example.com' },
    });
    fireEvent.change(document.querySelector('input[type="password"]') as HTMLElement, {
      target: { value: 'Str0ng-Passphrase' },
    });
    fireEvent.submit(document.querySelector('form') as HTMLFormElement);
  }

  it('creates a user with the documented body and returns to the list', async () => {
    const mock = stubFetch(() => json(201, {}));
    create();
    await waitFor(() => expect(visit).toHaveBeenCalledWith('/admin/users/'));
    const call = await sent(mock);
    expect(call.path).toBe('/api/users/admin');
    expect(JSON.parse(call.text)).toEqual({
      email: 'new@example.com',
      password: 'Str0ng-Passphrase',
      full_name: null,
      role_names: [],
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('shows the server detail when creation is refused', async () => {
    stubFetch(() => json(400, { detail: 'REGISTER_USER_ALREADY_EXISTS' }));
    create();
    expect(await screen.findByText('REGISTER_USER_ALREADY_EXISTS')).toBeInTheDocument();
    expect(visit).not.toHaveBeenCalled();
  });

  it('asks to try again when the request never reaches the server', async () => {
    stubFetch(() => {
      throw new TypeError('offline');
    });
    create();
    expect(await screen.findByText(keys.users.common.error_try_again)).toBeInTheDocument();
  });
});
