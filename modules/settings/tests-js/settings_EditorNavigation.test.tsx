import type { PendingVisit } from '@inertiajs/core';
import { configureI18n } from '@simple-module-py/i18n';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import ModulesEdit from '../settings/pages/ModulesEdit';
import type { ModuleView } from '../settings/ui/components/ModuleForm';

const mocks = vi.hoisted(() => ({
  before: undefined as undefined | ((event: { detail: { visit: PendingVisit } }) => boolean),
  navigate: undefined as undefined | ((event: { detail: { page: { url: string } } }) => void),
  reload: vi.fn(),
  replace: vi.fn(),
}));
vi.mock('@inertiajs/react', () => ({
  Head: () => null,
  router: {
    reload: mocks.reload,
    replace: mocks.replace,
    on: (name: 'before' | 'navigate', handler: never) => {
      mocks[name] = handler;
      return () => {
        mocks[name] = undefined;
      };
    },
  },
}));
vi.mock('@simple-module-py/ui/layouts/AdminLayout', () => ({ AdminLayout: () => null }));
configureI18n({
  locale: 'en',
  messages: {
    'settings.modules.search_placeholder': 'Search modules',
    'settings.modules.no_results': 'No matching modules',
    'settings.modules_form.save': 'Save',
    'settings.modules_form.saving': 'Saving',
    'settings.modules_form.reset_to_default': 'Revert',
    'settings.modules_form.discard_title': 'Discard changes?',
    'settings.modules_form.discard_changes': 'Discard changes',
    'settings.modules_form.leave_warning': 'You have unsaved changes. Discard them?',
    'settings.form.cancel_button': 'Cancel',
    'settings.modules.module_picker_label': 'Module',
  },
});
function moduleView(pkg: string): ModuleView {
  return {
    package: pkg,
    module_name: pkg,
    env_prefix: '',
    class_name: 'Settings',
    fields: [
      {
        name: 'sender',
        value: `${pkg} original`,
        default: '',
        db_override: true,
        type: 'string',
        description: '',
        is_secret: false,
        requires_restart: false,
        group: null,
        env_var: '',
      },
    ],
  };
}
const modules = [moduleView('users'), moduleView('mail')];
function visit(overrides: Partial<PendingVisit> = {}): PendingVisit {
  return {
    url: new URL(window.location.href),
    method: 'get',
    only: ['modules'],
    preserveState: true,
    ...overrides,
  } as PendingVisit;
}
beforeEach(() => {
  window.history.replaceState({}, '', '/admin/settings/');
  mocks.before = undefined;
  mocks.navigate = undefined;
  mocks.replace.mockImplementation(({ url }: { url: string }) => {
    window.history.replaceState({}, '', url);
  });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

test('opens a module URL and keeps the URL when switching and remounting', () => {
  window.history.replaceState({}, '', '/admin/settings/?module=mail');
  const { unmount } = render(<ModulesEdit modules={modules} />);
  expect(screen.getByLabelText('Sender')).toHaveValue('mail original');
  fireEvent.click(screen.getByRole('button', { name: /Users/ }));
  expect(new URL(window.location.href).searchParams.get('module')).toBe('users');
  unmount();
  render(<ModulesEdit modules={modules} />);
  expect(screen.getByLabelText('Sender')).toHaveValue('users original');
});

test('follows URLs restored by back/forward navigation', () => {
  render(<ModulesEdit modules={modules} />);
  act(() => {
    mocks.navigate?.({ detail: { page: { url: '/admin/settings/?module=mail' } } });
  });
  expect(screen.getByLabelText('Sender')).toHaveValue('mail original');
  act(() => {
    mocks.navigate?.({ detail: { page: { url: '/admin/settings/?module=users' } } });
  });
  expect(screen.getByLabelText('Sender')).toHaveValue('users original');
});

test('falls back to a visible module for an unknown query', () => {
  window.history.replaceState({}, '', '/admin/settings/?module=missing');
  const historyLength = window.history.length;
  render(<ModulesEdit modules={modules} />);
  expect(screen.getByLabelText('Sender')).toHaveValue('users original');
  expect(window.location.search).toBe('?module=users');
  expect(window.history.length).toBe(historyLength);
  expect(mocks.replace).toHaveBeenCalledWith({
    url: '/admin/settings/?module=users',
    preserveState: true,
    preserveScroll: true,
  });
});

test('normalizes an unknown module restored by navigation even when the fallback is already open', () => {
  render(<ModulesEdit modules={modules} />);
  act(() => {
    window.history.replaceState({}, '', '/admin/settings/?module=missing');
    mocks.navigate?.({ detail: { page: { url: '/admin/settings/?module=missing' } } });
  });
  expect(screen.getByLabelText('Sender')).toHaveValue('users original');
  expect(window.location.search).toBe('?module=users');
});

test('ignores a hidden module and preserves unrelated query parameters and fragments', () => {
  window.history.replaceState({}, '', '/admin/settings/?module=disabled&filter=active#fields');
  render(<ModulesEdit modules={[...modules, { ...moduleView('disabled'), fields: [] }]} />);
  expect(screen.getByLabelText('Sender')).toHaveValue('users original');
  expect(window.location.search).toBe('?module=users&filter=active');
  expect(window.location.hash).toBe('#fields');
  fireEvent.click(screen.getByRole('button', { name: /Mail/ }));
  expect(window.location.search).toBe('?module=mail&filter=active');
  expect(window.location.hash).toBe('#fields');
});

test('keeps the active module and its draft in an unmatched search', () => {
  render(<ModulesEdit modules={modules} />);
  fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'draft' } });
  fireEvent.change(screen.getByPlaceholderText('Search modules'), { target: { value: '(' } });
  expect(screen.getByRole('button', { name: /Users/ })).toHaveAttribute('aria-current', 'page');
  expect(screen.queryByRole('button', { name: /Mail/ })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Sender')).toHaveValue('draft');
  // Nothing matched, so say so even though the open module stays listed.
  expect(screen.getByRole('status')).toHaveTextContent('No matching modules');
});

test('search retains matches and follows the active module after switching', () => {
  render(<ModulesEdit modules={modules} />);
  fireEvent.change(screen.getByPlaceholderText('Search modules'), { target: { value: 'mail' } });
  expect(screen.getByRole('button', { name: /Users/ })).toHaveAttribute('aria-current', 'page');
  fireEvent.click(screen.getByRole('button', { name: /Mail/ }));
  expect(screen.getByRole('button', { name: /Mail/ })).toHaveAttribute('aria-current', 'page');
  expect(screen.queryByRole('button', { name: /Users/ })).not.toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText('Search modules'), { target: { value: '' } });
  expect(screen.getByRole('button', { name: /Users/ })).toBeVisible();
});

test('Cancel preserves a draft and focus; confirming switches module and URL', async () => {
  render(<ModulesEdit modules={modules} />);
  fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'draft' } });
  const mail = screen.getByRole('button', { name: /Mail/ });
  mail.focus();
  fireEvent.click(mail);
  expect(screen.getByRole('alertdialog')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('Sender')).toHaveValue('draft');
  expect(new URL(window.location.href).searchParams.get('module')).not.toBe('mail');
  await waitFor(() => expect(mail).toHaveFocus());
  fireEvent.click(mail);
  fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
  expect(screen.getByLabelText('Sender')).toHaveValue('mail original');
  expect(new URL(window.location.href).searchParams.get('module')).toBe('mail');
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  await waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveFocus());
});

test('guards refresh and leaving, but allows only the draft-preserving Revert reload', () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<ModulesEdit modules={modules} />);
  fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'draft' } });
  const unload = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(unload);
  expect(unload.defaultPrevented).toBe(true);
  const check = (overrides: Partial<PendingVisit>) =>
    mocks.before?.({ detail: { visit: visit(overrides) } });
  expect(check({})).toBe(true);
  expect(confirm).not.toHaveBeenCalled();
  expect(check({ url: new URL('http://localhost/admin/users/') })).toBe(false);
  expect(check({ only: [] })).toBe(false);
  expect(check({ preserveState: false })).toBe(false);
  expect(confirm).toHaveBeenCalledWith('You have unsaved changes. Discard them?');
});

test('blocks rapid repeated saves until the request resolves and preserves edits made during save', async () => {
  let resolve!: (response: Response) => void;
  const fetchMock = vi.fn(
    () =>
      new Promise<Response>((done) => {
        resolve = done;
      }),
  );
  vi.stubGlobal('fetch', fetchMock);
  render(<ModulesEdit modules={modules} />);
  const input = screen.getByLabelText('Sender');
  fireEvent.change(input, { target: { value: 'first draft' } });
  const save = screen.getByRole('button', { name: 'Save' });
  act(() => {
    for (let i = 0; i < 5; i++) save.click();
  });
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  expect(save).toBeDisabled();
  fireEvent.change(input, { target: { value: 'later draft' } });
  await act(async () => {
    resolve(new Response('{}', { status: 200 }));
  });
  expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
  expect(input).toHaveValue('later draft');
});

test.each(['validation', 'network'])(
  'allows retry after a %s failure and removes the guard after saving',
  async (failure) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    if (failure === 'network') fetchMock.mockRejectedValueOnce(new TypeError('Offline'));
    else
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: [{ loc: ['sender'], msg: 'Rejected' }] }), {
          status: 422,
        }),
      );
    vi.stubGlobal('fetch', fetchMock);
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(<ModulesEdit modules={modules} />);
    fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'draft' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByRole('alert')).toBeVisible());
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled());
    await waitFor(() => expect(mocks.before).toBeUndefined());
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: /Mail/ }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Sender')).toHaveValue('mail original');
    expect(confirm).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  },
);

// The phone picker is a Radix Select: opened from the keyboard, it lists the
// modules as options, and choosing one runs the same discard guard as the rail.
function pickOnPhone(name: string) {
  const trigger = screen.getByRole('combobox', { name: 'Module' });
  fireEvent.keyDown(trigger, { key: 'Enter' });
  fireEvent.keyDown(screen.getByRole('option', { name }), { key: 'Enter' });
}

test('the phone module picker goes through the same discard guard', () => {
  Element.prototype.scrollIntoView ??= () => {};
  Element.prototype.hasPointerCapture ??= () => false;
  render(<ModulesEdit modules={modules} />);
  fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'draft' } });
  pickOnPhone('Mail');
  expect(screen.getByRole('alertdialog')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  expect(screen.getByLabelText('Sender')).toHaveValue('draft');
  pickOnPhone('Mail');
  fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }));
  expect(screen.getByLabelText('Sender')).toHaveValue('mail original');
  expect(new URL(window.location.href).searchParams.get('module')).toBe('mail');
});
