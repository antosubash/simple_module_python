import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@simple-module-py/ui/components/ui/native-select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { UserMinus } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { useTenantErrors } from '../hooks/useTenantErrors';

export type MembershipRole = 'owner' | 'admin' | 'member';

export interface Member {
  user_id: string;
  email: string | null;
  role: MembershipRole;
  joined_at: string | null;
}

interface Props {
  members: Member[];
  myRole: MembershipRole;
  myUserId: string;
  canManage: boolean;
  tenantName: string;
  onChanged: () => void;
}

const ROLE_KEY = keys.tenants.roles;

/** The member roster on the Members page, with inline role edit / remove for managers. */
export function MembersTable({
  members,
  myRole,
  myUserId,
  canManage,
  tenantName,
  onChanged,
}: Props) {
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [savingId, setSavingId] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [leavingSelf, setLeavingSelf] = useState(false);

  async function changeRole(userId: string, role: MembershipRole) {
    setSavingId(userId);
    try {
      const response = await fetch(`/api/tenants/current/members/${userId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ role }),
      });
      if (!response.ok) {
        toast.error(await describe(response));
        return;
      }
      toast.success(t(keys.tenants.members.toast_role_updated));
      onChanged();
    } catch {
      toast.error(t(keys.tenants.errors.generic));
    } finally {
      setSavingId(null);
    }
  }

  async function confirmRemove() {
    if (!removing) return;
    const target = removing;
    setRemoving(null);
    try {
      const isSelf = target.user_id === myUserId;
      const url = isSelf
        ? '/api/tenants/current/membership'
        : `/api/tenants/current/members/${target.user_id}`;
      const response = await fetch(url, { method: 'DELETE', credentials: 'same-origin' });
      if (!response.ok) {
        toast.error(await describe(response));
        return;
      }
      if (isSelf) {
        toast.success(t(keys.tenants.members.toast_left));
        window.location.href = '/tenants';
        return;
      }
      toast.success(t(keys.tenants.members.toast_removed));
      onChanged();
    } catch {
      toast.error(t(keys.tenants.errors.generic));
    } finally {
      setLeavingSelf(false);
    }
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t(keys.tenants.members.table_email)}</TableHead>
            <TableHead>{t(keys.tenants.members.table_role)}</TableHead>
            <TableHead>{t(keys.tenants.members.table_joined)}</TableHead>
            {canManage && (
              <TableHead className="text-right">{t(keys.tenants.members.table_actions)}</TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((member) => {
            const isSelf = member.user_id === myUserId;
            const canEditThisRole = canManage && (myRole === 'owner' || member.role !== 'owner');
            return (
              <TableRow key={member.user_id}>
                <TableCell>
                  {member.email ?? member.user_id}
                  {isSelf && t(keys.tenants.members.you_suffix)}
                </TableCell>
                <TableCell>
                  {canEditThisRole ? (
                    <NativeSelect
                      size="sm"
                      value={member.role}
                      disabled={savingId === member.user_id}
                      onChange={(e) => changeRole(member.user_id, e.target.value as MembershipRole)}
                    >
                      {myRole === 'owner' && (
                        <NativeSelectOption value="owner">{t(ROLE_KEY.owner)}</NativeSelectOption>
                      )}
                      <NativeSelectOption value="admin">{t(ROLE_KEY.admin)}</NativeSelectOption>
                      <NativeSelectOption value="member">{t(ROLE_KEY.member)}</NativeSelectOption>
                    </NativeSelect>
                  ) : (
                    t(ROLE_KEY[member.role])
                  )}
                </TableCell>
                <TableCell>
                  {member.joined_at ? new Date(member.joined_at).toLocaleDateString() : '—'}
                </TableCell>
                {canManage && (
                  <TableCell className="text-right">
                    {isSelf ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive max-lg:min-h-11"
                        onClick={() => {
                          setLeavingSelf(true);
                          setRemoving(member);
                        }}
                      >
                        {t(keys.tenants.members.leave_button)}
                      </Button>
                    ) : (
                      member.role !== 'owner' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive max-lg:min-h-11"
                          onClick={() => setRemoving(member)}
                        >
                          <UserMinus className="size-4" aria-hidden="true" />
                          {t(keys.tenants.members.remove_button)}
                        </Button>
                      )
                    )}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      <ConfirmActionDialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRemoving(null);
            setLeavingSelf(false);
          }
        }}
        icon={UserMinus}
        title={
          leavingSelf
            ? t(keys.tenants.members.leave_confirm_title)
            : t(keys.tenants.members.remove_confirm_title)
        }
        description={
          leavingSelf
            ? t(keys.tenants.members.leave_confirm_description, { name: tenantName })
            : t(keys.tenants.members.remove_confirm_description, { name: tenantName })
        }
        confirmLabel={
          leavingSelf
            ? t(keys.tenants.members.leave_confirm_confirm)
            : t(keys.tenants.members.remove_confirm_confirm)
        }
        cancelLabel={
          leavingSelf
            ? t(keys.tenants.members.leave_confirm_cancel)
            : t(keys.tenants.members.remove_confirm_cancel)
        }
        onConfirm={confirmRemove}
      />
    </>
  );
}
