import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { useState } from 'react';
import { toast } from 'sonner';

/**
 * The per-row actions on the users table — resend, copy a reset link, and
 * disable or enable.
 *
 * Shared by the row's kebab menu and the invited row's inline "Resend", so
 * both spell the same request and report the same outcome. Each one reloads
 * the list afterwards rather than patching local state: the row's status pill,
 * the stat cards and the pending-invite count all move together, and keeping
 * three copies of that in the client is how they end up disagreeing.
 */
export function useUserRowActions() {
  const { t } = useT();
  const [busy, setBusy] = useState<string | null>(null);

  async function copyToClipboard(text: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Clipboard access is denied over plain http and in some embedded
      // browsers. The caller says so rather than reporting a silent success.
      return false;
    }
  }

  async function resendInvite(userId: string, email: string) {
    setBusy(userId);
    try {
      const resp = await fetch(`/api/users/admin/${userId}/resend-invite`, { method: 'POST' });
      if (!resp.ok) {
        toast.error(t(keys.users.user_row.toast_resend_failed));
        return;
      }
      const body = await resp.json();
      // A mailer that only logs hands back the link instead: putting it on the
      // clipboard is the difference between "invited" and "actually reachable".
      if (body.status === 'link' && body.link) {
        const copied = await copyToClipboard(body.link);
        toast.success(
          copied
            ? t(keys.users.user_row.toast_resend_link)
            : t(keys.users.user_row.toast_resent, { email }),
        );
      } else {
        toast.success(t(keys.users.user_row.toast_resent, { email }));
      }
      router.reload();
    } catch {
      toast.error(t(keys.users.common.error_occurred));
    } finally {
      setBusy(null);
    }
  }

  async function copyResetLink(userId: string) {
    setBusy(userId);
    try {
      const resp = await fetch(`/api/users/admin/${userId}/reset-password-link`, {
        method: 'POST',
      });
      if (!resp.ok) {
        toast.error(t(keys.users.user_row.toast_reset_failed));
        return;
      }
      const body = await resp.json();
      const copied = await copyToClipboard(body.link ?? '');
      if (copied) toast.success(t(keys.users.user_row.toast_reset_copied));
      else toast.error(t(keys.users.user_row.toast_reset_failed));
    } catch {
      toast.error(t(keys.users.common.error_occurred));
    } finally {
      setBusy(null);
    }
  }

  async function setActive(userId: string, active: boolean) {
    setBusy(userId);
    try {
      const resp = await fetch(`/api/users/admin/${userId}/${active ? 'enable' : 'disable'}`, {
        method: 'PATCH',
      });
      if (!resp.ok) {
        toast.error(t(keys.users.user_row.toast_status_failed));
        return;
      }
      toast.success(
        active ? t(keys.users.user_row.toast_enabled) : t(keys.users.user_row.toast_disabled),
      );
      router.reload();
    } catch {
      toast.error(t(keys.users.common.error_occurred));
    } finally {
      setBusy(null);
    }
  }

  return { busy, resendInvite, copyResetLink, setActive };
}

export type UserRowActions = ReturnType<typeof useUserRowActions>;
