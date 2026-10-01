/**
 * The organisation settings row writes through the active-tenant endpoint —
 * never a URL carrying a tenant id — and only offers "reset" when the tenant
 * actually holds an override (#382).
 */
import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, test, vi } from 'vitest';
import { type TenantSetting, TenantSettingRow } from '../tenants/components/TenantSettingRow';

configureI18n({
  locale: 'en',
  messages: {
    'tenants.settings.save': 'Save',
    'tenants.settings.reset': 'Reset to platform value',
    'tenants.settings.overridden': 'Overridden',
    'tenants.settings.inherited': 'Platform value',
    'tenants.settings.inherited_value': 'Platform value: {value}',
    'tenants.settings.none': '(empty)',
    'tenants.settings.toast_saved': 'Setting saved',
    'tenants.settings.toast_reset': 'Setting reset',
    'tenants.settings.toast_failed': 'Could not save',
    'tenants.settings.toast_uploaded': 'Image uploaded',
    'branding.tenant_settings.app_name': 'Nom de l’application',
  },
});

const base: TenantSetting = {
  key: 'demo.motto',
  description: 'A motto',
  value_type: 'string',
  inherited: 'hi',
  value: null,
  effective: 'hi',
  upload_url: '',
};

afterEach(() => vi.restoreAllMocks());

describe('TenantSettingRow', () => {
  test('saving PUTs the draft to the current-tenant endpoint', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }));
    const onChanged = vi.fn();
    render(<TenantSettingRow setting={base} onChanged={onChanged} />);

    await userEvent.type(screen.getByLabelText('demo.motto'), 'ours');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/tenant/current/demo.motto',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ value: 'ours' }) }),
    );
    expect(onChanged).toHaveBeenCalled();
  });

  test('reset is offered only for an override', () => {
    const { rerender } = render(<TenantSettingRow setting={base} onChanged={() => {}} />);
    expect(screen.queryByRole('button', { name: 'Reset to platform value' })).toBeNull();
    expect(screen.getByText('Platform value: hi')).toBeInTheDocument();

    rerender(<TenantSettingRow setting={{ ...base, value: 'ours' }} onChanged={() => {}} />);
    expect(screen.getByRole('button', { name: 'Reset to platform value' })).toBeInTheDocument();
    expect(screen.getByText('Overridden')).toBeInTheDocument();
  });

  test('a file-id key offers an upload, not a text box for the id', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{}', { status: 200 }));
    const setting = {
      ...base,
      key: 'branding.logo_file_id',
      upload_url: '/api/branding/tenant/logo',
    };
    render(<TenantSettingRow setting={setting} onChanged={() => {}} />);

    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
    const file = new File(['png'], 'logo.png', { type: 'image/png' });
    await userEvent.upload(screen.getByLabelText('branding.logo_file_id'), file);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/branding/tenant/logo',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('the description is translated by its key, with the English as fallback', () => {
    const { rerender } = render(
      <TenantSettingRow
        setting={{ ...base, description_key: 'branding.tenant_settings.app_name' }}
        onChanged={() => {}}
      />,
    );
    expect(screen.getByText('Nom de l’application')).toBeInTheDocument();

    rerender(
      <TenantSettingRow
        setting={{ ...base, description_key: 'branding.tenant_settings.unknown' }}
        onChanged={() => {}}
      />,
    );
    expect(screen.getByText('A motto')).toBeInTheDocument();
  });
});
