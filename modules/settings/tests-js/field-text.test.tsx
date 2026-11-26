import { configureI18n } from '@simple-module-py/i18n';
import { renderHook } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import {
  groupSlug,
  humanize,
  settingsText,
  useSettingsText,
} from '../settings/ui/utils/field-text';

describe('humanize', () => {
  test('spells acronyms in capitals and keeps the rest in sentence case', () => {
    expect(humanize('smtp_tls_mode')).toBe('SMTP TLS mode');
    expect(humanize('s3_endpoint_url')).toBe('S3 endpoint URL');
    expect(humanize('jwks_cache_ttl_seconds')).toBe('JWKS cache TTL seconds');
    expect(humanize('file_storage')).toBe('File storage');
  });
});

test('groupSlug lowercases and joins runs of other characters with one underscore', () => {
  expect(groupSlug('Demo account')).toBe('demo_account');
  expect(groupSlug(' Google OAuth ')).toBe('google_oauth');
  expect(groupSlug('S3')).toBe('s3');
});

describe('settingsText fallback chain', () => {
  const catalog: Record<string, string> = {
    'mail.settings_form.title': 'Mail',
    'mail.settings_form.fields.smtp_host.label': 'SMTP server',
    'mail.settings_form.fields.smtp_host.help': 'Host name of your mail server.',
    'mail.settings_form.groups.demo_account': 'Demo account',
  };
  const text = settingsText('mail', (key) => catalog[key]);

  test('a locale key wins', () => {
    expect(text.title()).toBe('Mail');
    expect(text.label({ name: 'smtp_host', title: 'Ignored' })).toBe('SMTP server');
    expect(text.help({ name: 'smtp_host', description: 'Ignored' })).toBe(
      'Host name of your mail server.',
    );
    expect(text.group('Demo account')).toBe('Demo account');
  });

  test('then the declared title and description', () => {
    expect(text.label({ name: 'smtp_port', title: 'Port' })).toBe('Port');
    expect(text.help({ name: 'smtp_port', description: 'Usually 587.' })).toBe('Usually 587.');
  });

  test('then a humanised identifier, and no help at all', () => {
    expect(text.label({ name: 'smtp_tls_mode' })).toBe('SMTP TLS mode');
    expect(text.help({ name: 'smtp_tls_mode', description: '' })).toBeUndefined();
    expect(settingsText('file_storage', () => undefined).title()).toBe('File storage');
    expect(text.group('Raw group')).toBe('Raw group');
  });
});

test('useSettingsText reads the active catalog', () => {
  configureI18n({
    locale: 'en',
    messages: { 'tenants.settings_form.fields.subdomain_base.label': 'Subdomain base' },
  });
  const { result } = renderHook(() => useSettingsText('tenants'));
  expect(result.current.label({ name: 'subdomain_base' })).toBe('Subdomain base');
  expect(result.current.label({ name: 'invitation_ttl_hours' })).toBe('Invitation TTL hours');
});
