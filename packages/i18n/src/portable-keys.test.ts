import { expect, it } from 'vitest';
import { keys as appKeys } from '../../../host/client_app/i18n/keys.generated';
import { keys as moduleKeys } from '../../../modules/users/users/pages/i18n.generated';
import { keys as compatibilityKeys, configureI18n, t } from './index';

it('module, app and compatibility keys agree and translate through the public API', () => {
  const key = moduleKeys.users.accept_invite.head_title;
  expect(key).toBe('users.accept_invite.head_title');
  expect(appKeys.users.accept_invite.head_title).toBe(key);
  expect(compatibilityKeys.users.accept_invite.head_title).toBe(key);
  expect(Object.keys(moduleKeys)).toEqual(['users']);
  configureI18n({ locale: 'en', messages: { [key]: 'Accept invite' } });
  expect(t(key)).toBe('Accept invite');
});

it('registers an app namespace on the compatibility export before old pages render', async () => {
  const { registerTranslationKeys } = await import('./index');
  registerTranslationKeys({ external_catalog: { title: 'external_catalog.title' } });
  expect(Reflect.get(compatibilityKeys, 'external_catalog')).toEqual({
    title: 'external_catalog.title',
  });
});
