import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
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
