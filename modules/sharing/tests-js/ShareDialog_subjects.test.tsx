import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ShareDialog } from '../sharing/ui';

configureI18n({ locale: 'en', messages: {} });
afterEach(() => vi.unstubAllGlobals());

it('offers registered types and uses translated tenant-role labels', async () => {
  let body: unknown;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      if (request.url.includes('/subject-types'))
        return Response.json([
          { subject_type: 'user', label_key: 'sharing.subjects.user' },
          { subject_type: 'tenant_role', label_key: 'sharing.subjects.tenant_role' },
        ]);
      if (request.url.includes('/candidates'))
        return Response.json([
          { id: 'member', display_name: 'tenant:member', email: '', subject_type: 'tenant_role' },
        ]);
      if (request.method === 'POST') {
        body = await request.json();
        return Response.json({
          id: 's',
          subject_id: 'member',
          subject_type: 'tenant_role',
          role: 'view',
        });
      }
      return Response.json([]);
    }),
  );
  render(<ShareDialog resourceType="notes.note" resourceId="one" />);
  fireEvent.click(screen.getByRole('button', { name: keys.sharing.dialog.button }));
  const dialog = await screen.findByRole('dialog');
  const picker = await within(dialog).findByLabelText(keys.sharing.dialog.subject_type);
  expect(within(picker).getAllByRole('option')).toHaveLength(2);
  fireEvent.change(picker, { target: { value: 'tenant_role' } });
  fireEvent.change(within(dialog).getByLabelText(keys.sharing.dialog.search_label), {
    target: { value: 'member' },
  });
  expect(await within(dialog).findByText(keys.sharing.subjects.member)).toBeVisible();
  fireEvent.click(within(dialog).getByRole('button', { name: keys.sharing.dialog.grant }));
  await within(dialog).findByRole('button', { name: keys.sharing.dialog.revoke_for });
  expect(body).toMatchObject({ subject_type: 'tenant_role', subject_id: 'member' });
});

it('keeps the type picker hidden when only one provider is available', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) =>
      Response.json(
        request.url.includes('/subject-types')
          ? [{ subject_type: 'user', label_key: 'sharing.subjects.user' }]
          : [],
      ),
    ),
  );
  render(<ShareDialog resourceType="notes.note" resourceId="one" />);
  fireEvent.click(screen.getByRole('button', { name: keys.sharing.dialog.button }));
  await screen.findByText(keys.sharing.dialog.none);
  expect(screen.queryByLabelText(keys.sharing.dialog.subject_type)).toBeNull();
});
