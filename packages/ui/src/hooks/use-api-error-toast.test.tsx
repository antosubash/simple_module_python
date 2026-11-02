import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const error = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (msg: string) => error(msg) } }));
vi.mock('@simple-module-py/i18n', () => ({ useT: () => ({ t: (key: string) => `t:${key}` }) }));

import { failure, success } from '../lib/api-result';
import { useApiErrorToast } from './use-api-error-toast';

describe('useApiErrorToast', () => {
  beforeEach(() => error.mockClear());

  it('toasts the server detail, else the fallback key', () => {
    const show = renderHook(() => useApiErrorToast('ui.errors.generic' as never)).result.current;
    show(failure(409, { detail: 'Already taken' }));
    show(failure(500, null));
    expect(error.mock.calls).toEqual([['Already taken'], ['t:ui.errors.generic']]);
  });

  it('stays quiet on success', () => {
    const show = renderHook(() => useApiErrorToast('ui.errors.generic' as never)).result.current;
    show(success(200, {}));
    expect(error).not.toHaveBeenCalled();
  });
});
