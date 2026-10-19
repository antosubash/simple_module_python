import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.save': 'Save',
    'settings.modules_form.saved_toast': 'Settings saved',
    'settings.modules_form.invalid_json': 'Not valid JSON',
    'settings.modules_form.not_set': 'Not set (default)',
    'settings.modules.heading_suffix': 'settings',
    'settings.modules.unsaved_count_one': '{count} unsaved',
    'settings.modules.unsaved_count_other': '{count} unsaved',
  },
});

vi.mock('@inertiajs/react', () => ({ router: { reload: vi.fn() } }));

import type { FieldMeta } from '../settings/pages/components/FieldInput';
import { ModuleForm } from '../settings/pages/components/ModuleForm';

function field(overrides: Partial<FieldMeta> & { name: string }): FieldMeta {
  return {
    type: 'json',
    value: null,
    default: null,
    description: '',
    is_secret: false,
    requires_restart: false,
    group: null,
    env_var: `SM_BG_TASKS_${overrides.name.toUpperCase()}`,
    choices: null,
    ...overrides,
  };
}

function renderForm(fields: FieldMeta[]) {
  render(
    <ModuleForm
      module={{
        module_name: 'Background tasks',
        package: 'background_tasks',
        env_prefix: 'SM_BG_TASKS_',
        class_name: 'BackgroundTasksSettings',
        fields,
      }}
    />,
  );
}

async function savedBody(fetchMock: ReturnType<typeof vi.fn>) {
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  return JSON.parse(fetchMock.mock.calls[0][1].body);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('JSON-typed fields (GH #487)', () => {
  test('a dict field is sent as the parsed object, not its text', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    renderForm([field({ name: 'task_routes_override', value: {}, input_type: 'json' })]);

    fireEvent.change(screen.getByLabelText('task_routes_override'), {
      target: { value: '{"reports.*": "heavy"}' },
    });

    expect(await savedBody(fetchMock)).toEqual({ task_routes_override: { 'reports.*': 'heavy' } });
  });

  test('unparseable JSON is flagged before save', () => {
    renderForm([field({ name: 'task_routes_override', value: {}, input_type: 'json' })]);

    fireEvent.change(screen.getByLabelText('task_routes_override'), { target: { value: '{' } });

    expect(screen.getByText('Not valid JSON')).toBeVisible();
  });

  test('an unset int | None is an empty number box, not the text "null"', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    renderForm([field({ name: 'worker_concurrency', input_type: 'int', nullable: true })]);

    const input = screen.getByLabelText('worker_concurrency');
    expect(input).toHaveValue(null);
    expect(input).toHaveAttribute('type', 'number');

    fireEvent.change(input, { target: { value: '4' } });
    expect(await savedBody(fetchMock)).toEqual({ worker_concurrency: 4 });
  });

  test('clearing an int | None sends null', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    renderForm([
      field({ name: 'worker_concurrency', value: 4, input_type: 'int', nullable: true }),
    ]);

    fireEvent.change(screen.getByLabelText('worker_concurrency'), { target: { value: '' } });
    expect(await savedBody(fetchMock)).toEqual({ worker_concurrency: null });
  });

  test('a bool | None offers "not set" instead of a two-state switch', () => {
    renderForm([field({ name: 'task_reject_on_worker_lost', input_type: 'bool', nullable: true })]);

    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveTextContent('Not set (default)');
  });
});

describe('JsonInput', () => {
  test('replaces its text when the value changes from outside', async () => {
    const { JsonInput } = await import('../settings/pages/components/JsonInput');
    const props = { name: 'routes', nullable: false, className: '', onChange: vi.fn() };
    const { rerender } = render(<JsonInput {...props} value={{ a: 'b' }} />);
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '{"x": "y"}' } });

    rerender(<JsonInput {...props} value={{}} />);

    expect(screen.getByRole('textbox')).toHaveValue('{}');
  });
});
