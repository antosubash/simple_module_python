import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Alert, AlertDescription } from '@simple-module-py/ui/components/ui/alert';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { currentCsrfToken } from '@simple-module-py/ui/lib/csrf-token';
import { TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

export interface LinkedSignIn {
  id: string;
  provider: string;
  username: string | null;
  subject: string | null;
  last_sign_in_at: string | null;
}

interface Props {
  userId: string;
  links: LinkedSignIn[];
  hasDuplicates: boolean;
}

/** Inspect and remove individual identity-provider links (#877, #1149). */
export function LinkedSignInsCard({ userId, links, hasDuplicates }: Props) {
  const { t } = useT();
  const { ago } = useRelativeTime();
  const [pending, setPending] = useState<LinkedSignIn | null>(null);
  const [removing, setRemoving] = useState(false);

  function confirmRemove() {
    if (!pending) return;
    const onFailure = () => {
      toast.error(t(keys.users.linked_sign_ins.remove_failed));
      return false;
    };
    router.delete(`/admin/users/${userId}/linked-sign-ins/${pending.id}`, {
      headers: { 'X-CSRF-Token': currentCsrfToken() ?? '' },
      // Keep unsaved details intact: only the link list needs fresh props.
      only: ['linked_sign_ins', 'has_duplicate_linked_sign_ins'],
      preserveScroll: true,
      preserveState: true,
      onStart: () => setRemoving(true),
      onSuccess: () => toast.success(t(keys.users.linked_sign_ins.removed)),
      onError: onFailure,
      onHttpException: onFailure,
      onNetworkError: onFailure,
      onFinish: () => {
        setRemoving(false);
        setPending(null);
      },
    });
  }

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.linked_sign_ins.title)}</SectionTitle>
        {hasDuplicates && (
          <Alert className="mb-4 border-amber-500/40 bg-amber-500/5">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>{t(keys.users.linked_sign_ins.duplicates)}</AlertDescription>
          </Alert>
        )}
        <ul className="space-y-3 text-sm">
          {links.map((link) => (
            <li key={link.id} className="space-y-0.5">
              <div className="flex items-center justify-between gap-3">
                <p className="font-medium">
                  {link.provider}
                  {link.username && (
                    <span className="font-normal text-muted-foreground"> · {link.username}</span>
                  )}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="max-lg:min-h-11"
                  disabled={removing}
                  onClick={() => setPending(link)}
                >
                  {t(keys.users.linked_sign_ins.remove)}
                </Button>
              </div>
              {link.subject && (
                <p className="break-all text-xs text-muted-foreground">
                  {t(keys.users.linked_sign_ins.subject)} <code>{link.subject}</code>
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                {link.last_sign_in_at
                  ? t(keys.users.linked_sign_ins.last_sign_in, { when: ago(link.last_sign_in_at) })
                  : t(keys.users.linked_sign_ins.never)}
              </p>
            </li>
          ))}
        </ul>
      </CardContent>
      <ConfirmActionDialog
        open={pending !== null}
        onOpenChange={(open) => !removing && !open && setPending(null)}
        icon={TriangleAlert}
        title={t(keys.users.linked_sign_ins.confirm_title, { provider: pending?.provider ?? '' })}
        description={t(keys.users.linked_sign_ins.confirm_body)}
        confirmLabel={t(keys.users.linked_sign_ins.remove)}
        cancelLabel={t(keys.users.common.cancel)}
        busy={removing}
        onConfirm={confirmRemove}
      />
    </Card>
  );
}
