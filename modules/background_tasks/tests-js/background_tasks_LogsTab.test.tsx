import '@testing-library/jest-dom/vitest';
import { configureI18n, keys } from '@simple-module-py/i18n';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

configureI18n({ locale: 'en', messages: {} });

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { LogsPanel } from '../background_tasks/pages/components/LogsPanel';
import { requestsOf, stubFetch } from './stub-fetch';

const line = (message: string, level_name = 'INFO', level = 20) => ({
  id: message,
  ts: '2026-01-01T00:00:00Z',
  level,
  level_name,
  logger: 'demo',
  message,
  task_id: 'c1',
  job_id: null,
  tenant_id: null,
  correlation_id: null,
});

describe('LogsPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads a task's lines and refetches with the chosen minimum level", async () => {
    const fetchMock = stubFetch(200, {
      items: [line('copied 3 rows'), line('disk full', 'ERROR', 40)],
      total: 2,
      page: 1,
      per_page: 50,
    });
    render(<LogsPanel executionId="e1" />);
    const urls = () => requestsOf(fetchMock).map((c) => c.url);

    expect(await screen.findByText('copied 3 rows')).toBeInTheDocument();
    expect(screen.getByText('disk full')).toBeInTheDocument();
    expect(urls()[0]).toBe('/api/background_tasks/admin/executions/e1/logs?page=1');

    fireEvent.change(
      screen.getByRole('combobox', { name: keys.background_tasks.logs.level_label }),
      { target: { value: 'ERROR' } },
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(urls()[1]).toContain('level=ERROR');
  });

  it('says why it is empty when nothing was retained', async () => {
    stubFetch(200, { items: [], total: 0, page: 1, per_page: 50 });
    render(<LogsPanel executionId="e1" />);
    expect(await screen.findByText(keys.background_tasks.logs.empty_title)).toBeInTheDocument();
  });
});
