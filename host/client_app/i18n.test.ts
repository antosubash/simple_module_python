import { beforeEach, expect, it, vi } from 'vitest';

const { handlers, reload, language, update } = vi.hoisted(() => ({
  handlers: {} as {
    before: (event: { detail: { visit: { headers: Record<string, string> } } }) => void;
    success: (event: {
      detail: {
        page: {
          props: {
            i18n: {
              locale: string;
              audience: string;
              messages: Record<string, string> | null;
            };
          };
        };
      };
    }) => void;
  },
  reload: vi.fn(),
  language: { value: 'en' },
  update: vi.fn(),
}));
vi.mock('@inertiajs/react', () => ({
  router: {
    on: vi.fn((name, handler) => {
      handlers[name] = handler;
      return vi.fn();
    }),
    reload,
  },
}));
vi.mock('@simple-module-py/i18n', () => ({
  configureI18n: vi.fn(),
  activeLocale: () => language.value,
  updateI18n: update,
}));

import { bootI18nFromInitialPage, subscribeI18nToNavigation } from './i18n';

beforeEach(() => {
  vi.clearAllMocks();
  language.value = 'en';
  bootI18nFromInitialPage({
    i18n: { locale: 'en', audience: 'public', supportedLocales: ['en'], messages: {} },
  });
  subscribeI18nToNavigation();
});

it('sends the catalog held by this tab and updates its audience after login', () => {
  const visit = { headers: {} as Record<string, string> };
  handlers.before({ detail: { visit } });
  expect(visit.headers['X-SM-I18n']).toBe('en:public');
  handlers.success({
    detail: { page: { props: { i18n: { locale: 'en', audience: 'full', messages: {} } } } },
  });
  handlers.before({ detail: { visit } });
  expect(visit.headers['X-SM-I18n']).toBe('en:full');
  expect(update).toHaveBeenCalledWith({ locale: 'en', messages: {} });
});

it('reloads a missing catalog once and keeps advertising the catalog it holds', () => {
  const event = {
    detail: { page: { props: { i18n: { locale: 'de', audience: 'public', messages: null } } } },
  };
  handlers.success(event);
  handlers.success(event);
  expect(reload).toHaveBeenCalledTimes(1);
  expect(reload).toHaveBeenCalledWith(expect.objectContaining({ only: ['i18n'] }));
  const visit = { headers: {} as Record<string, string> };
  handlers.before({ detail: { visit } });
  expect(visit.headers['X-SM-I18n']).toBe('en:public');
});

it('does not reload a matching locale with omitted messages', () => {
  handlers.success({
    detail: { page: { props: { i18n: { locale: 'en', audience: 'public', messages: null } } } },
  });
  expect(reload).not.toHaveBeenCalled();
  expect(update).not.toHaveBeenCalled();
});

it('resets the retry guard after receiving a catalog', () => {
  const missing = {
    detail: { page: { props: { i18n: { locale: 'de', audience: 'public', messages: null } } } },
  };
  handlers.success(missing);
  handlers.success({
    detail: { page: { props: { i18n: { locale: 'de', audience: 'public', messages: {} } } } },
  });
  language.value = 'de';
  handlers.success({
    detail: { page: { props: { i18n: { locale: 'es', audience: 'public', messages: null } } } },
  });
  expect(reload).toHaveBeenCalledTimes(2);
});

it('forces catalog delivery on recovery when the initial page had no audience', () => {
  bootI18nFromInitialPage({});
  const visit = { headers: {} as Record<string, string> };
  handlers.before({ detail: { visit } });
  expect(visit.headers).toEqual({});
  handlers.success({
    detail: { page: { props: { i18n: { locale: 'de', audience: 'public', messages: null } } } },
  });
  handlers.before({ detail: { visit } });
  expect(visit.headers['X-SM-I18n']).toBe('');
});
