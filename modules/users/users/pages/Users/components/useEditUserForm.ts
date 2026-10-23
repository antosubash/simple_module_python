import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { useLeaveGuard } from '@simple-module-py/ui/hooks/useLeaveGuard';
import { apiResult, NETWORK_FAILURE } from '@simple-module-py/ui/lib/api';
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { api } from '../../api';

export interface EditableUser {
  id: string;
  email: string;
  full_name: string | null;
  roles: string[];
}

interface FormState {
  email: string;
  fullName: string;
  roles: string[];
}

function sameRoles(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const sortedB = [...b].sort();
  return [...a].sort().every((role, i) => role === sortedB[i]);
}

/**
 * One dirty state and one Save covering details and roles.
 *
 * They were three independent forms with three save buttons, so a
 * half-finished edit could be abandoned in a way the page never acknowledged,
 * and "did that save?" had three different answers.
 */
export function useEditUserForm(user: EditableUser) {
  const { t } = useT();

  const initial = useMemo<FormState>(
    () => ({
      email: user.email,
      fullName: user.full_name ?? '',
      roles: user.roles ?? [],
    }),
    [user.email, user.full_name, user.roles],
  );

  const [form, setForm] = useState<FormState>(initial);
  // What is currently persisted. Starts at the server's values and advances
  // per section as each save lands, so "unsaved changes" stays truthful even
  // when only part of a save succeeded.
  const [baseline, setBaseline] = useState<FormState>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-seed after a server reload, or the form would keep showing pre-save
  // values against a record that has already moved on.
  useEffect(() => {
    setForm(initial);
    setBaseline(initial);
    setError(null);
  }, [initial]);

  const emailDirty = form.email !== baseline.email;
  const nameDirty = form.fullName !== baseline.fullName;
  const rolesDirty = !sameRoles(form.roles, baseline.roles);
  const detailsDirty = emailDirty || nameDirty;
  // Roles count as one change however many chips moved: the save is one
  // request, and "5 unsaved changes" for one toggled role would overstate it.
  const dirtyCount = Number(emailDirty) + Number(nameDirty) + Number(rolesDirty);

  // Set while this page is driving its own visit (the post-save reload), so
  // the guard below doesn't prompt about changes that were just persisted —
  // React has not re-rendered with the advanced baseline at that point.
  const savingRef = useRef(false);

  useLeaveGuard(dirtyCount > 0, t(keys.users.edit.leave_warning), savingRef);

  const toggleRole = (roleName: string) =>
    setForm((prev) => ({
      ...prev,
      roles: prev.roles.includes(roleName)
        ? prev.roles.filter((r) => r !== roleName)
        : [...prev.roles, roleName],
    }));

  async function save() {
    setSaving(true);
    setError(null);
    savingRef.current = true;
    try {
      // Only the parts that changed — sending roles untouched would rewrite
      // every assignment's audit trail for an edit that never touched them.
      //
      // The baseline advances per section as each one lands. If details save
      // and roles then fail, the page must stop calling the details edit
      // "unsaved" — it is already persisted, and saying otherwise invites the
      // admin to redo work or distrust the indicator entirely.
      if (detailsDirty) {
        const resp = await apiResult(
          api.PATCH('/api/users/admin/{user_id}', {
            params: { path: { user_id: user.id } },
            body: { email: form.email, full_name: form.fullName || null },
          }),
        );
        if (!resp.ok) {
          setError(
            resp.status === NETWORK_FAILURE
              ? t(keys.users.common.error_occurred)
              : (resp.detail ?? t(keys.users.edit.error_details)),
          );
          return;
        }
        setBaseline((prev) => ({ ...prev, email: form.email, fullName: form.fullName }));
      }
      if (rolesDirty) {
        const resp = await apiResult(
          api.PUT('/api/users/admin/{user_id}/roles', {
            params: { path: { user_id: user.id } },
            body: { role_names: form.roles },
          }),
        );
        if (!resp.ok) {
          setError(
            resp.status === NETWORK_FAILURE
              ? t(keys.users.common.error_occurred)
              : detailsDirty
                ? t(keys.users.edit.error_partial)
                : t(keys.users.edit.error_roles),
          );
          return;
        }
        setBaseline((prev) => ({ ...prev, roles: form.roles }));
      }
      toast.success(t(keys.users.edit.toast_saved));
      router.reload();
    } finally {
      setSaving(false);
      savingRef.current = false;
    }
  }

  return {
    form,
    setForm,
    dirtyCount,
    saving,
    error,
    toggleRole,
    save,
    discard: () => setForm(baseline),
  };
}
