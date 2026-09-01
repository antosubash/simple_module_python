import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, test, vi } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'settings.modules_form.saved_toast': 'Settings saved',
  },
});

const mocks = vi.hoisted(() => ({ reload: vi.fn() }));

vi.mock('@inertiajs/react', () => ({
  router: { reload: mocks.reload },
}));

import { ModuleForm, type ModuleView } from '../settings/pages/components/ModuleForm';

const moduleView: ModuleView = {
  module_name: 'BackgroundTasks',
  package: 'background_tasks',
  env_prefix: 'SM_BG_TASKS_',
  class_name: 'BackgroundTasksSettings',
  fields: [
    {
      name: 'retention_days',
      type: 'int',
      value: 14,
      default: 14,
      description: '',
      is_secret: false,
      requires_restart: false,
      group: null,
      env_var: 'SM_BG_TASKS_RETENTION_DAYS',
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('ModuleForm', () => {
  test('shows success feedback after settings are saved', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal('fetch', fetchMock);
    render(<ModuleForm module={moduleView} />);

    fireEvent.change(screen.getByLabelText('retention_days'), { target: { value: '30' } });
    fireEvent.click(screen.getByRole('button', { name: /modules_form\.save$/ }));

    await waitFor(() => expect(screen.getByRole('status')).toBeVisible());
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/settings/modules/background_tasks',
      expect.objectContaining({ body: JSON.stringify({ retention_days: 30 }) }),
    );
    expect(mocks.reload).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved');
  });
});
