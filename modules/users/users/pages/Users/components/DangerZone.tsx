import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@simple-module-py/ui/components/ui/alert-dialog';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { Trash2 } from 'lucide-react';
import { useId, useState } from 'react';
import { toast } from 'sonner';

interface Props {
  userId: string;
  email: string;
  isSelf: boolean;
}

export function DangerZone({ userId, email, isSelf }: Props) {
  const { t } = useT();
  const [deleting, setDeleting] = useState(false);
  // Deleting a user is unrecoverable and the row it starts from looks like
  // every other row, so the confirm asks for the address to be typed out.
  // Reading it back is the part that catches "wrong person" — a second click
  // never would.
  const [typed, setTyped] = useState('');
  const confirmId = useId();
  const confirmed = typed.trim().toLowerCase() === email.toLowerCase();

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
      })
      .catch(() => {
        toast.error(t(keys.users.common.error_occurred));
        setDeleting(false);
      });
  };

  return (
    <Card className="border-destructive/40 lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.danger_zone.title)}</SectionTitle>
        {isSelf ? (
          <p className="text-sm text-muted-foreground">{t(keys.users.danger_zone.self_note)}</p>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm text-muted-foreground">{t(keys.users.danger_zone.description)}</p>
            <AlertDialog onOpenChange={(open) => !open && setTyped('')}>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" size="sm" className="gap-1.5" disabled={deleting}>
                  <Trash2 className="h-3.5 w-3.5" />
                  {deleting
                    ? t(keys.users.danger_zone.deleting)
                    : t(keys.users.danger_zone.delete_button)}
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    {t(keys.users.danger_zone.confirm_title, { email })}
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    {t(keys.users.danger_zone.confirm_body)}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <div className="grid gap-2">
                  <Label htmlFor={confirmId} className="text-sm font-normal">
                    {t(keys.users.danger_zone.confirm_prompt_prefix)}{' '}
                    <span className="font-medium text-foreground">{email}</span>{' '}
                    {t(keys.users.danger_zone.confirm_prompt_suffix)}
                  </Label>
                  <Input
                    id={confirmId}
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    autoComplete="off"
                    placeholder={email}
                  />
                </div>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t(keys.users.common.cancel)}</AlertDialogCancel>
                  <AlertDialogAction disabled={!confirmed} onClick={handleDelete}>
                    {t(keys.users.danger_zone.delete_button)}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
