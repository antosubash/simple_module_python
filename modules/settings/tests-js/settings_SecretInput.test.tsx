import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
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

test('new secrets stay hidden, toggle visibility, and Cancel restores the unchanged mask', () => {
  render(<ModuleForm module={module} />);
  const maskedValue = (screen.getByLabelText('password') as HTMLInputElement).value;
  fireEvent.click(screen.getByRole('button', { name: 'Set new value' }));
  const control = screen.getByLabelText('password');
  expect(control).toHaveAttribute('type', 'password');
  expect(control).not.toHaveAttribute('readonly');
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
