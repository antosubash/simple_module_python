import { keys, useT } from '@simple-module-py/i18n';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { useState } from 'react';
import { toast } from 'sonner';
import { api } from '../../api';
import { adminFailureMessage } from '../../failureMessage';

/**
 * The immediate account actions on the edit page — disable/enable, mark
 * verified, copy a reset link.
 *
 * They are deliberately not part of the page's dirty state: locking out a
 * compromised account should not require finding a Save button. Keeping them
 * here leaves the page itself to own only the details/roles form.
 */
export function useUserActions(
  userId: string,
  initialActive: boolean,
  initialVerified: boolean,
  initialLockedUntil: string | null,
) {
  const { t } = useT();
  const [isActive, setIsActive] = useState(initialActive);
  const [isVerified, setIsVerified] = useState(initialVerified);
  const [lockedUntil, setLockedUntil] = useState(initialLockedUntil);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingVerify, setSavingVerify] = useState(false);

  const patch = (
    call: Promise<{ response: Response; data?: unknown; error?: unknown }>,
    onSuccess: () => void,
    okMsg: string,
    failMsg: string,
  ) => {
    setSavingStatus(true);
    apiResult(call)
      .then((res) => {
        if (res.ok) {
          onSuccess();
          toast.success(okMsg);
        } else {
          toast.error(adminFailureMessage(res, failMsg, t(keys.users.common.error_occurred), t));
        }
      })
      .finally(() => setSavingStatus(false));
  };

  const params = { params: { path: { user_id: userId } } };

  const disable = () =>
    patch(
      api.PATCH('/api/users/admin/{user_id}/disable', params),
      () => setIsActive(false),
      t(keys.users.edit.toast_disabled),
      t(keys.users.edit.toast_disable_failed),
    );

  const enable = () =>
    patch(
      api.PATCH('/api/users/admin/{user_id}/enable', params),
      () => setIsActive(true),
      t(keys.users.edit.toast_enabled),
      t(keys.users.edit.toast_enable_failed),
    );

  const unlock = () =>
    patch(
      api.PATCH('/api/users/admin/{user_id}/unlock', params),
      () => setLockedUntil(null),
      t(keys.users.edit.toast_unlocked),
      t(keys.users.edit.toast_unlock_failed),
    );

  const markVerified = () => {
    setSavingVerify(true);
    apiResult(api.PATCH('/api/users/admin/{user_id}/verify', params))
      .then((res) => {
        if (res.ok) {
          setIsVerified(true);
          toast.success(t(keys.users.edit.toast_verified));
        } else {
          toast.error(
            adminFailureMessage(
              res,
              t(keys.users.edit.toast_verify_failed),
              t(keys.users.common.error_occurred),
              t,
            ),
          );
        }
      })
      .finally(() => setSavingVerify(false));
  };

  const copyResetLink = () => {
    apiResult(api.POST('/api/users/admin/{user_id}/reset-password-link', params))
      .then(async (res) => {
        if (res.ok) {
          await navigator.clipboard.writeText(res.data?.link ?? '');
          toast.success(t(keys.users.edit.toast_reset_copied));
        } else {
          toast.error(
            adminFailureMessage(
              res,
              t(keys.users.edit.toast_reset_failed),
              t(keys.users.common.error_occurred),
              t,
            ),
          );
        }
      })
      .catch(() => toast.error(t(keys.users.common.error_occurred)));
  };

  return {
    isActive,
    isVerified,
    lockedUntil,
    savingStatus,
    savingVerify,
    disable,
    enable,
    unlock,
    markVerified,
    copyResetLink,
  };
}
