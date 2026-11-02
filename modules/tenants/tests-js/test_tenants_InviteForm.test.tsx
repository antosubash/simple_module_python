import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { InviteForm } from '../tenants/components/InviteForm';

configureI18n({
  locale: 'en',
  messages: {
    'tenants.members.invite_email_label': 'Email',
    'tenants.members.invite_submit': 'Send invitation',
    'tenants.members.invite_email_invalid': 'Enter a valid email address.',
    'tenants.members.invite_link_copy': 'Copy link',
    'tenants.members.invite_emailed': 'Invitation emailed to {email}',
    'tenants.members.invite_share_link': 'Not emailed — share this link',
  },
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test.each([true, false])('keeps the link and copy button when emailed=%s', async (emailed) => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        accept_url: '/tenants/invitations/accept?token=secret',
        email: 'friend@example.com',
        emailed,
      }),
      { status: 201 },
    ),
  );
  const onInvited = vi.fn();
  render(<InviteForm onInvited={onInvited} />);
  await userEvent.type(screen.getByLabelText('Email'), 'friend@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
  expect(
    await screen.findByText(
      emailed ? 'Invitation emailed to friend@example.com' : 'Not emailed — share this link',
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      new URL('/tenants/invitations/accept?token=secret', window.location.origin).toString(),
    ),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Copy link' })).toBeInTheDocument();
  expect(onInvited).toHaveBeenCalledOnce();
});

test('an invalid email shows a translated inline error and sends nothing (#575)', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch');
  render(<InviteForm onInvited={vi.fn()} />);
  await userEvent.type(screen.getByLabelText('Email'), 'notanemail');
  await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
  expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('a server error is not flagged on the email field; a client error clears on edit', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ detail: 'already_member' }), { status: 409 }),
  );
  render(<InviteForm onInvited={vi.fn()} />);
  const input = screen.getByLabelText('Email');
  await userEvent.type(input, 'friend@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
  await screen.findByText(keys.tenants.errors.already_member);
  expect(input).not.toHaveAttribute('aria-invalid');

  await userEvent.clear(input);
  await userEvent.type(input, 'notanemail');
  await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
  expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
  expect(input).toHaveAttribute('aria-invalid', 'true');

  await userEvent.type(input, 'x');
  expect(screen.queryByText('Enter a valid email address.')).not.toBeInTheDocument();
  expect(input).not.toHaveAttribute('aria-invalid');
});
