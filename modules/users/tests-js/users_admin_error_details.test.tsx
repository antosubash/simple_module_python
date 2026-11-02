import { configureI18n, t } from '@simple-module-py/i18n';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@inertiajs/react', () => ({ router: { reload: vi.fn(), on: vi.fn(() => vi.fn()) } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from 'sonner';
import { useUserRowActions } from '../users/admin/components/useUserRowActions';
import de from '../users/locales/de.json';
import en from '../users/locales/en.json';
import { adminFailureMessage } from '../users/pages/failureMessage';
import { useEditUserForm } from '../users/pages/Users/components/useEditUserForm';
import { useUserActions } from '../users/pages/Users/components/useUserActions';
import { json, stubFetch } from './users_fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe.each(['en', 'de'])('users admin errors (%s)', (locale) => {
  function configure() {
    const messages: Record<string, string> = {};
    function flatten(value: object, prefix = 'users') {
      for (const [key, child] of Object.entries(value)) {
        if (typeof child === 'string') messages[`${prefix}.${key}`] = child;
        else flatten(child, `${prefix}.${key}`);
      }
    }
    flatten(locale === 'en' ? en : de);
    configureI18n({ locale, messages });
  }

  const privileged = () =>
    locale === 'en'
      ? 'You cannot manage a more privileged account.'
      : 'Sie können kein Konto mit höheren Berechtigungen verwalten.';

  it.each(['row', 'edit'])('translates the server refusal in the %s action toast', async (page) => {
    configure();
    stubFetch(() => json(403, { detail: 'You cannot manage a more privileged account.' }));
    const { result } = renderHook(() => {
      const row = useUserRowActions();
      const edit = useUserActions('target', true, false, null);
      return { row, edit };
    });
    await act(async () => {
      if (page === 'row') await result.current.row.setActive('target', false);
      else result.current.edit.disable();
    });
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(privileged()));
    expect(result.current.edit.isActive).toBe(true);
  });

  it.each([false, true])(
    'explains a refused role grant after details saved: %s',
    async (detailsDirty) => {
      configure();
      stubFetch((request) =>
        request.method === 'PATCH'
          ? json(200, {})
          : json(403, { detail: 'You cannot assign roles you do not hold.' }),
      );
      const user = { id: 'target', email: 'a@example.com', full_name: null, roles: [] };
      const { result } = renderHook(() => useEditUserForm(user));
      act(() => {
        result.current.toggleRole('Admin');
        if (detailsDirty) result.current.setForm((prev) => ({ ...prev, fullName: 'New name' }));
      });
      await act(async () => result.current.save());
      const reason =
        locale === 'en'
          ? 'You cannot assign roles you do not hold.'
          : 'Sie können keine Rollen zuweisen, die Sie selbst nicht innehaben.';
      expect(result.current.error).toBe(
        detailsDirty ? `${(locale === 'en' ? en : de).edit.error_partial} ${reason}` : reason,
      );
      expect(result.current.dirtyCount).toBe(1);
    },
  );

  it.each(Object.entries(en.admin_errors))('translates the known refusal %s', (key, detail) => {
    configure();
    expect(adminFailureMessage({ status: 400, detail }, 'fallback', 'network', t)).toBe(
      (locale === 'en' ? en : de).admin_errors[key as keyof typeof en.admin_errors],
    );
  });

  it.each([null, '', 'constructor', 'unexpected server internals', [{ msg: 'invalid' }]])(
    'keeps the fallback for unknown detail %s',
    async (detail) => {
      configure();
      stubFetch(() => json(400, { detail }));
      const { result } = renderHook(() => useUserRowActions());
      await act(async () => result.current.setActive('target', false));
      expect(toast.error).toHaveBeenCalledWith(
        (locale === 'en' ? en : de).user_row.toast_status_failed,
      );
    },
  );

  it('keeps the network failure message', async () => {
    configure();
    stubFetch(() => {
      throw new TypeError('offline');
    });
    const { result } = renderHook(() => useUserRowActions());
    await act(async () => result.current.setActive('target', false));
    expect(toast.error).toHaveBeenCalledWith((locale === 'en' ? en : de).common.error_occurred);
  });
});
