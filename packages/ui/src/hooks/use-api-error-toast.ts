import { type TranslationKey, useT } from '@simple-module-py/i18n';
import { useCallback } from 'react';
import { toast } from 'sonner';
import type { ApiResult } from '../lib/api-result';

/**
 * Opt-in error toast for an `api.*` / `apiFetch` result (#504): the server's
 * string `detail` when it sent one, else `t(fallbackKey)`. A successful result
 * shows nothing, so callers can pass every result through.
 */
export function useApiErrorToast(fallbackKey: TranslationKey) {
  const { t } = useT();
  return useCallback(
    (result: ApiResult<unknown>): void => {
      if (!result.ok) toast.error(result.detail ?? t(fallbackKey));
    },
    [t, fallbackKey],
  );
}
