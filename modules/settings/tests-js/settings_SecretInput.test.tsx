import { configureI18n } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { ModuleForm, type ModuleView } from '../settings/ui/components/ModuleForm';

vi.mock('@inertiajs/react', () => ({ router: { reload: vi.fn() } }));
configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.save': 'Save',
    'settings.modules_form.set_new_value': 'Set new value',
    'settings.modules_form.show_secret': 'Show secret',
    'settings.modules_form.hide_secret': 'Hide secret',
    'settings.form.cancel_button': 'Cancel',
  },
});
const module: ModuleView = {
  package: 'mail',
  module_name: 'Mail',
  env_prefix: 'SM_MAIL_',
  class_name: 'MailSettings',
  fields: [
    {
      name: 'password',
      type: 'string',
      value: '••••••••',
      default: '',
      description: 'Mail password',
      is_secret: true,
      requires_restart: false,
      group: null,
      env_var: 'SM_MAIL_PASSWORD',
    },
  ],
};

afterEach(() => vi.unstubAllGlobals());

test('new secrets stay hidden, toggle visibility, and Cancel restores the unchanged mask', () => {
  render(<ModuleForm module={module} />);
  const maskedValue = (screen.getByLabelText('password') as HTMLInputElement).value;
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  const control = screen.getByLabelText('password');
  expect(control).toHaveAttribute('type', 'password');
  expect(control).not.toHaveAttribute('readonly');
  expect(control).toHaveAttribute('autocomplete', 'new-password');
  expect(control).toHaveValue('');
  fireEvent.change(control, { target: { value: 'new-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Show secret' }));
  expect(control).toHaveAttribute('type', 'text');
  fireEvent.click(screen.getByRole('button', { name: 'Hide secret' }));
  expect(control).toHaveAttribute('type', 'password');
  fireEvent.click(screen.getByRole('button', { name: 'Show secret' }));
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('password')).toHaveAttribute('readonly');
  expect(screen.getByLabelText('password')).toHaveValue(maskedValue);
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  expect(screen.getByLabelText('password')).toHaveAttribute('type', 'password');
  expect(screen.getByLabelText('password')).toHaveValue('');
});

test('Cancel cannot restore the old mask while a new secret is being saved', async () => {
  let resolve!: (response: Response) => void;
  const fetchMock = vi.fn(
    (_request: Request) =>
      new Promise<Response>((done) => {
        resolve = done;
      }),
  );
  vi.stubGlobal('fetch', fetchMock);
  render(<ModuleForm module={module} />);
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  fireEvent.change(screen.getByLabelText('password'), { target: { value: 'new-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const cancel = screen.getByRole('button', { name: 'Cancel' });
  expect(cancel).toBeDisabled();
  expect(screen.getByLabelText('password')).toBeDisabled();
  act(() => cancel.click());
  await act(async () => resolve(new Response('{}', { status: 200 })));
  expect(cancel).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  fireEvent.click(cancel);
  expect(screen.getByLabelText('password')).toHaveAttribute('readonly');
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  const request = fetchMock.mock.calls[0]?.[0] as Request | undefined;
  expect(await request?.json()).toEqual({ password: 'new-secret' });
});
