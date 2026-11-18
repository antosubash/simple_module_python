import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ShareDialog } from '../sharing/ui';

configureI18n({ locale: 'en', messages: {} });
let held: boolean;
let grantedBody: unknown;
let mutationGate: Promise<void> | undefined;
beforeEach(() => {
  mutationGate = undefined;
  held = false;
  grantedBody = null;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      if (request.method === 'POST') {
        await mutationGate;
        held = true;
        grantedBody = await request.json();
      }
      if (request.method === 'DELETE') {
        held = false;
        return new Response(null, { status: 204 });
      }
      if (request.url.includes('/candidates'))
        return Response.json([{ id: 'friend', display_name: 'Friend', email: 'friend@test' }]);
      const share = {
        id: 'share',
        resource_type: 'notes.note',
        resource_id: 'note',
        subject_type: 'user',
        subject_id: 'friend',
        subject_label: 'Friend',
        role: 'reviewer',
        granted_by: 'owner',
        granted_by_label: null,
        expires_at: null,
        expired: false,
        created_at: null,
      };
      return Response.json(request.method === 'POST' ? share : held ? [share] : []);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

it('renders, searches, grants a custom role and revokes it', async () => {
  render(
    <ShareDialog
      resourceType="notes.note"
      resourceId="note"
      roles={[{ value: 'reviewer', label: 'Reviewer' }]}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: keys.sharing.dialog.button }));
  const dialog = await screen.findByRole('dialog');
  expect(within(dialog).getByText(keys.sharing.dialog.title)).toBeInTheDocument();
  await waitFor(() =>
    expect(within(dialog).getByText(keys.sharing.dialog.none)).toBeInTheDocument(),
  );
  fireEvent.change(within(dialog).getByLabelText(keys.sharing.dialog.search_label), {
    target: { value: 'friend' },
  });
  fireEvent.click(await within(dialog).findByRole('button', { name: keys.sharing.dialog.grant }));
  await waitFor(() =>
    expect(within(dialog).queryByRole('button', { name: keys.sharing.dialog.grant })).toBeNull(),
  );
  expect(within(dialog).getAllByText('Reviewer').length).toBeGreaterThan(0);
  expect(grantedBody).toMatchObject({ subject_id: 'friend', role: 'reviewer' });
  fireEvent.click(within(dialog).getByRole('button', { name: keys.sharing.dialog.revoke_for }));
  await waitFor(() =>
    expect(within(dialog).getByText(keys.sharing.dialog.none)).toBeInTheDocument(),
  );
});

it('keeps pending grants visible through dismissal attempts and reopening', async () => {
  let finish!: () => void;
  mutationGate = new Promise<void>((resolve) => {
    finish = resolve;
  });
  render(<ShareDialog resourceType="notes.note" resourceId="note" />);
  const trigger = screen.getByRole('button', { name: keys.sharing.dialog.button });
  fireEvent.click(trigger);
  const dialog = await screen.findByRole('dialog');
  await waitFor(() => expect(within(dialog).getByText(keys.sharing.dialog.none)).toBeVisible());
  fireEvent.change(within(dialog).getByLabelText(keys.sharing.dialog.search_label), {
    target: { value: 'friend' },
  });
  fireEvent.click(await within(dialog).findByRole('button', { name: keys.sharing.dialog.grant }));
  const close = within(dialog).getByRole('button', { name: keys.sharing.dialog.close });
  expect(close).toBeDisabled();
  fireEvent.click(close);
  fireEvent.keyDown(dialog, { key: 'Escape' });
  const overlay = document.querySelector('[data-slot="dialog-overlay"]');
  if (!overlay) throw new Error('Missing dialog overlay');
  fireEvent.pointerDown(overlay, { button: 0, ctrlKey: false });
  expect(screen.getByRole('dialog')).toBeVisible();
  finish();
  await waitFor(() => expect(close).toBeEnabled());
  expect(within(dialog).getByText('Friend')).toBeVisible();
  fireEvent.click(close);
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  fireEvent.click(trigger);
  expect(await screen.findByText('Friend')).toBeVisible();
  expect(screen.queryByText(keys.sharing.dialog.none)).toBeNull();
});
