import { keys, useT } from '@simple-module-py/i18n';
import { useState } from 'react';
import { toast } from 'sonner';

/**
 * The immediate account actions on the edit page — disable/enable, mark
 * verified, copy a reset link.
 *
 * They are deliberately not part of the page's dirty state: locking out a
 * compromised account should not require finding a Save button. Keeping them
 * here leaves the page itself to own only the details/roles form.
 */
export function useUserActions(userId: string, initialActive: boolean, initialVerified: boolean) {
  const { t } = useT();
  const [isActive, setIsActive] = useState(initialActive);
  const [isVerified, setIsVerified] = useState(initialVerified);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingVerify, setSavingVerify] = useState(false);

  const patch = (url: string, onSuccess: () => void, okMsg: string, failMsg: string) => {
    setSavingStatus(true);
    fetch(url, { method: 'PATCH' })
      .then((res) => {
        if (res.ok) {
          onSuccess();
          toast.success(okMsg);
        } else {
          toast.error(failMsg);
        }
      })
      .catch(() => toast.error(t(keys.users.common.error_occurred)))
      .finally(() => setSavingStatus(false));
  };

  const disable = () =>
    patch(
      `/api/users/admin/${userId}/disable`,
      () => setIsActive(false),
      t(keys.users.edit.toast_disabled),
      t(keys.users.edit.toast_disable_failed),
    );

  const enable = () =>
    patch(
      `/api/users/admin/${userId}/enable`,
      () => setIsActive(true),
      t(keys.users.edit.toast_enabled),
      t(keys.users.edit.toast_enable_failed),
    );

  const markVerified = () => {
    setSavingVerify(true);
    fetch(`/api/users/admin/${userId}/verify`, { method: 'PATCH' })
      .then((res) => {
        if (res.ok) {
          setIsVerified(true);
          toast.success(t(keys.users.edit.toast_verified));
        } else {
          toast.error(t(keys.users.edit.toast_verify_failed));
        }
      })
      .catch(() => toast.error(t(keys.users.common.error_occurred)))
      .finally(() => setSavingVerify(false));
  };

  const copyResetLink = () => {
    fetch(`/api/users/admin/${userId}/reset-password-link`, { method: 'POST' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          await navigator.clipboard.writeText(data.link ?? data.url ?? '');
          toast.success(t(keys.users.edit.toast_reset_copied));
        } else {
          toast.error(t(keys.users.edit.toast_reset_failed));
        }
      })
      .catch(() => toast.error(t(keys.users.common.error_occurred)));
  };

  return {
    isActive,
    isVerified,
    savingStatus,
    savingVerify,
    disable,
    enable,
    markVerified,
    copyResetLink,
  };
}
