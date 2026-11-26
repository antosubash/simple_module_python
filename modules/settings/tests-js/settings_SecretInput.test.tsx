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
  const maskedValue = (screen.getByLabelText('Password') as HTMLInputElement).value;
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  const control = screen.getByLabelText('Password');
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
  expect(screen.getByLabelText('Password')).toHaveAttribute('readonly');
  expect(screen.getByLabelText('Password')).toHaveValue(maskedValue);
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
  expect(screen.getByLabelText('Password')).toHaveValue('');
});

test('a saved secret returns to its mask and an empty draft is never sent', async () => {
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
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'new-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const cancel = screen.getByRole('button', { name: 'Cancel' });
  expect(cancel).toBeDisabled();
  expect(screen.getByLabelText('Password')).toBeDisabled();
  act(() => cancel.click());
  await act(async () => resolve(new Response('{}', { status: 200 })));
  expect(screen.getByLabelText('Password')).toHaveAttribute('readonly');
  expect(screen.getByLabelText('Password')).toHaveValue('••••••••••');
  expect(screen.queryByDisplayValue('new-secret')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  const request = fetchMock.mock.calls[0]?.[0] as Request | undefined;
  expect(await request?.json()).toEqual({ password: 'new-secret' });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'second-secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText('Password')).toBeDisabled();
  await act(async () => resolve(new Response('{}', { status: 200 })));
  expect(screen.getByLabelText('Password')).toHaveAttribute('readonly');
  expect(await fetchMock.mock.calls[1]?.[0].json()).toEqual({ password: 'second-secret' });
});

test.each(['validation', 'server', 'network'])(
  'secret controls unlock after a %s failure and retry keeps the draft',
  async (failure) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    if (failure === 'network') fetchMock.mockRejectedValueOnce(new TypeError('Offline'));
    else
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: [{ loc: ['password'], msg: 'Rejected' }] }), {
          status: failure === 'validation' ? 422 : 500,
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    render(<ModuleForm module={module} />);
    fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
    const control = screen.getByLabelText('Password');
    fireEvent.change(control, { target: { value: 'new-secret' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeVisible());
    expect(control).toBeEnabled();
    expect(control).toHaveValue('new-secret');
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Show secret' })).toBeEnabled();
    expect(control).toHaveAccessibleDescription(
      failure === 'validation' ? 'Mail password Rejected' : 'Mail password',
    );
    const ids = control.getAttribute('aria-describedby')?.split(' ') ?? [];
    for (const id of ids) expect(document.getElementById(id)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByLabelText('Password')).toHaveAttribute('readonly'));
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription('Mail password');
    expect(screen.getByLabelText('Password')).not.toHaveAttribute('aria-invalid', 'true');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    for (const [request] of fetchMock.mock.calls) {
      expect(await (request as Request).json()).toEqual({ password: 'new-secret' });
    }
  },
);
