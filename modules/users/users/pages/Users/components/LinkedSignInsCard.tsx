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
import { useCallback, useEffect, useRef, useState } from 'react';
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
  const heading = useRef<HTMLHeadingElement>(null);
  const removeButtons = useRef(new Map<string, HTMLButtonElement>());
  const focusOrder = useRef<string[]>([]);
  const lastFocus = useRef<HTMLElement | null>(null);
  const restoreFocus = useCallback(() => {
    const target =
      focusOrder.current.map((id) => removeButtons.current.get(id)).find(Boolean) ??
      heading.current;
    target?.focus();
    lastFocus.current = target ?? null;
  }, []);

  // A failed removal's refresh can remove the stale row after the dialog closes.
  useEffect(() => {
    if (
      lastFocus.current &&
      !lastFocus.current.isConnected &&
      document.activeElement === document.body
    ) {
      restoreFocus();
    }
  });

  function confirmRemove() {
    if (!pending) return;
    const onFailure = () => {
      toast.error(t(keys.users.linked_sign_ins.remove_failed));
      return false;
    };
    const onHttpFailure = (response: { status: number }) => {
      onFailure();
      // A 404 means another tab already removed the link: refresh the list only.
      // Any other status (403, expired session) must not trigger a visit that
      // could swap the page and drop unsaved details.
      if (response.status === 404) {
        router.reload({
          only: ['linked_sign_ins', 'has_duplicate_linked_sign_ins'],
          onHttpException: () => false,
          onNetworkError: () => false,
        });
      }
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
      onHttpException: onHttpFailure,
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
        <SectionTitle ref={heading} tabIndex={-1}>
          {t(keys.users.linked_sign_ins.title)}
        </SectionTitle>
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
                  ref={(button) => {
                    if (button) removeButtons.current.set(link.id, button);
                    else removeButtons.current.delete(link.id);
                  }}
                  variant="outline"
                  size="sm"
                  className="max-lg:min-h-11"
                  disabled={removing}
                  onClick={() => {
                    const index = links.indexOf(link);
                    focusOrder.current = [
                      link,
                      ...links.slice(index + 1),
                      ...links.slice(0, index).reverse(),
                    ].map((row) => row.id);
                    setPending(link);
                  }}
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
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          restoreFocus();
        }}
        icon={TriangleAlert}
        title={t(keys.users.linked_sign_ins.confirm_title, { provider: pending?.provider ?? '' })}
        description={
          <>
            {t(keys.users.linked_sign_ins.confirm_body)}
            {links.length === 1 && <> {t(keys.users.linked_sign_ins.last_link_warning)}</>}
          </>
        }
        confirmLabel={t(keys.users.linked_sign_ins.remove)}
        cancelLabel={t(keys.users.common.cancel)}
        busy={removing}
        onConfirm={confirmRemove}
      />
    </Card>
  );
}
