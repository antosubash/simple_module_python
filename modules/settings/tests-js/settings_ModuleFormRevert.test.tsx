import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import type { FieldMeta } from '../settings/pages/components/FieldInput';
import { ModuleForm, type ModuleView } from '../settings/pages/components/ModuleForm';
import ModulesEdit from '../settings/pages/ModulesEdit';

const mocks = vi.hoisted(() => ({ reload: vi.fn() }));
vi.mock('@inertiajs/react', () => ({ router: { reload: mocks.reload }, Head: () => null }));
configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.save': 'Save',
    'settings.modules_form.saved_toast': 'Saved',
    'settings.modules_form.reset_to_default': 'Revert',
    'settings.modules.unsaved_count_one': '{count} unsaved',
  },
});

function field(name: string, value: string, db_override = false): FieldMeta {
  return {
    name,
    value,
    db_override,
    type: 'string',
    default: '',
    description: '',
    is_secret: false,
    requires_restart: false,
    group: null,
    env_var: 'SM_TEST_FIELD',
    env_set: false,
    env_readable: false,
    choices: null,
  };
}
function view(fields: FieldMeta[]): ModuleView {
  return {
    module_name: 'Users',
    package: 'users',
    env_prefix: 'SM_USERS_',
    class_name: 'UsersSettings',
    fields,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

test('reverting one field preserves other drafts and their saved baseline after props reload', async () => {
  const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  const { rerender } = render(
    <ModuleForm
      module={view([field('smtp_host', 'override', true), field('sender', 'original')])}
    />,
  );
  fireEvent.change(screen.getByLabelText('sender'), { target: { value: 'draft' } });
  fireEvent.change(screen.getByLabelText('smtp_host'), { target: { value: 'discard me' } });
  fireEvent.click(screen.getByRole('button', { name: 'Revert' }));
  await waitFor(() => expect(mocks.reload).toHaveBeenCalled());
  rerender(
    <ModuleForm module={view([field('smtp_host', 'default'), field('sender', 'original')])} />,
  );
  expect(screen.getByLabelText('smtp_host')).toHaveValue('default');
  expect(screen.getByLabelText('sender')).toHaveValue('draft');
  expect(screen.getByText('1 unsaved')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const [request] = fetchMock.mock.calls[1] as unknown as [Request];
  expect(await request.json()).toEqual({ sender: 'draft' });
});

test('switching modules starts a fresh edit buffer even when field names match', () => {
  const users = view([field('sender', 'users original')]);
  const mail = {
    ...view([field('sender', 'mail original')]),
    module_name: 'Mail',
    package: 'mail',
  };
  render(<ModulesEdit modules={[users, mail]} />);
  fireEvent.change(screen.getByLabelText('sender'), { target: { value: 'users draft' } });
  fireEvent.click(screen.getByRole('button', { name: /mail/ }));
  expect(screen.getByLabelText('sender')).toHaveValue('mail original');
  expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
});

test('saving a defaulted field immediately offers Revert and keeps confirmation visible', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 200 })),
  );
  render(<ModuleForm module={view([field('sender', '')])} />);
  expect(screen.queryByRole('button', { name: 'Revert' })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('sender'), { target: { value: 'new sender' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByRole('button', { name: 'Revert' })).toBeVisible();
  expect(screen.getByRole('status')).toHaveTextContent('Saved');
});

test('saving the default removes Revert without changing other fields', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 200 })),
  );
  render(
    <ModuleForm
      module={view([field('sender', 'override', true), field('host', 'stored', true)])}
    />,
  );
  fireEvent.change(screen.getByLabelText('sender'), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Saved'));
  expect(screen.getAllByRole('button', { name: 'Revert' })).toHaveLength(1);
});

test('a failed save keeps a defaulted field without Revert', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 422 })),
  );
  render(<ModuleForm module={view([field('sender', '')])} />);
  fireEvent.change(screen.getByLabelText('sender'), { target: { value: 'rejected' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled());
  expect(screen.queryByRole('button', { name: 'Revert' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('sender')).toHaveValue('rejected');
});

test('revert right after a save shows the live default and hides Revert', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('{}', { status: 200 })),
  );
  const fields = [{ ...field('sender', 'default-sender'), default: 'default-sender' }];
  mocks.reload.mockImplementation((options: { onSuccess?: (page: unknown) => void }) => {
    options.onSuccess?.({ props: { modules: [view(fields)] } });
  });
  render(<ModuleForm module={view(fields)} />);
  const input = screen.getByDisplayValue('default-sender');
  fireEvent.change(input, { target: { value: 'custom' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  const revert = await screen.findByRole('button', { name: 'Revert' });
  fireEvent.click(revert);
  await waitFor(() => expect(screen.getByDisplayValue('default-sender')).toBeInTheDocument());
  expect(screen.queryByRole('button', { name: 'Revert' })).not.toBeInTheDocument();
});
