import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Trash2 } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface Props {
  userId: string;
  email: string;
  isSelf: boolean;
}

/**
 * Deleting the account.
 *
 * Red-tinted rather than merely red-bordered, and an outline button rather
 * than a filled one: the card is the warning, and a solid destructive button
 * inside a solid destructive panel is the loudest thing on a page whose point
 * is that you should not click it by accident.
 *
 * The confirm asks for the address to be typed out. Reading it back is what
 * catches "wrong person"; a second click never would.
 */
export function DangerZone({ userId, email, isSelf }: Props) {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = () => {
    setDeleting(true);
    fetch(`/api/users/admin/${userId}`, { method: 'DELETE' })
      .then(async (res) => {
        if (res.ok) {
          toast.success(t(keys.users.danger_zone.toast_deleted));
          router.visit('/admin/users/');
          return; // navigating away — leave `deleting` set
        }
        const data = await res.json().catch(() => ({}));
        toast.error(
          typeof data?.detail === 'string' ? data.detail : t(keys.users.danger_zone.toast_failed),
        );
        setDeleting(false);
        setOpen(false);
      })
      .catch(() => {
        toast.error(t(keys.users.common.error_occurred));
        setDeleting(false);
        setOpen(false);
      });
  };

  return (
    <Card className="border-red-500/40 bg-red-500/5">
      <CardContent className="flex h-full flex-col gap-2.5 pt-5">
        <h2 className="text-[15px] font-bold text-red-600 font-[var(--font-display)] dark:text-red-400">
          {t(keys.users.danger_zone.title)}
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {t(keys.users.danger_zone.description)}
        </p>
        <div className="mt-auto pt-2">
          {/* Disabled rather than hidden for your own account: the copy above
              says deletion is blocked there, and a button that simply is not
              on the page leaves that sentence unexplained. */}
          <Button
            variant="outline"
            disabled={isSelf || deleting}
            onClick={() => setOpen(true)}
            className="gap-1.5 border-red-500 text-red-600 hover:bg-red-500/10 hover:text-red-700 max-lg:min-h-11 dark:text-red-400 dark:hover:text-red-300"
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
            {deleting
              ? t(keys.users.danger_zone.deleting)
              : t(keys.users.danger_zone.delete_button)}
          </Button>
          {isSelf && (
            <p className="mt-2 text-xs text-muted-foreground">
              {t(keys.users.danger_zone.self_note)}
            </p>
          )}
        </div>
      </CardContent>

      <ConfirmActionDialog
        // Pinned while the request is in flight: the Radix action closes on
        // click, and the dialog vanishing mid-delete looks like it worked.
        open={open || deleting}
        onOpenChange={(next) => !deleting && setOpen(next)}
        icon={Trash2}
        title={t(keys.users.danger_zone.confirm_title, { email })}
        description={t(keys.users.danger_zone.confirm_body)}
        confirmLabel={t(keys.users.danger_zone.delete_button)}
        cancelLabel={t(keys.users.common.cancel)}
        confirmText={{
          expected: email,
          label: `${t(keys.users.danger_zone.confirm_prompt_prefix)} ${email} ${t(keys.users.danger_zone.confirm_prompt_suffix)}`,
          placeholder: email,
        }}
        busy={deleting}
        onConfirm={handleDelete}
      />
    </Card>
  );
}
