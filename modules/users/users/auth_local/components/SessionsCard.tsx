import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { describeUserAgent } from '@simple-module-py/ui/lib/user-agent';
import { LogOut } from 'lucide-react';
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

interface Props {
  lastLoginAt: string | null;
}

/**
 * This browser, and the one control that reaches the others.
 *
 * The deck lists every device with its user agent and IP. This app cannot:
 * browser auth is a signed cookie, not a server-side session store, so there
 * is no row per device to list or revoke. Inventing a list would be worse than
 * showing one honest entry — and "Sign out everywhere" is real regardless,
 * because it bumps a counter every session carries and the auth provider
 * checks.
 */
export function SessionsCard({ lastLoginAt }: Props) {
  const { t } = useT();
  const { ago } = useRelativeTime();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  // Read in an effect rather than during render: `navigator` does not exist
  // while the page is server-rendered, and naming the browser in the first
  // client render would make it disagree with the markup it is hydrating.
  const [agent, setAgent] = useState<{ browser: string; os: string } | null>(null);
  useEffect(() => setAgent(describeUserAgent(navigator.userAgent)), []);

  async function revokeAll() {
    setBusy(true);
    try {
      const resp = await fetch('/api/users/me/sessions/revoke-all', { method: 'POST' });
      if (!resp.ok) {
        toast.error(t(keys.users.profile.toast_signed_out_failed));
        setBusy(false);
        setConfirming(false);
        return;
      }
      // This browser is signed out too, so a full page load is the point —
      // an Inertia visit would carry a session the server has just refused.
      window.location.assign('/users/login');
    } catch {
      toast.error(t(keys.users.common.error_occurred));
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.profile.sessions_title)}</SectionTitle>
        <div className="flex items-center gap-3 text-sm">
          <span className="size-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <div>
              {agent
                ? t(keys.users.profile.this_browser_on, { browser: agent.browser, os: agent.os })
                : t(keys.users.profile.this_browser)}
            </div>
            <div className="text-xs text-muted-foreground">
              {lastLoginAt
                ? t(keys.users.profile.signed_in_ago, { ago: ago(lastLoginAt) })
                : t(keys.users.profile.signed_in_now)}
            </div>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="mt-4 text-sm font-medium text-red-600 transition-colors hover:text-red-700 max-lg:min-h-11 dark:text-red-400 dark:hover:text-red-300"
        >
          {t(keys.users.profile.sign_out_everywhere)}
        </button>
      </CardContent>

      <ConfirmActionDialog
        // Pinned while the request is in flight: the Radix action closes on
        // click, and this one navigates away rather than re-rendering.
        open={confirming || busy}
        onOpenChange={(next) => !busy && setConfirming(next)}
        icon={LogOut}
        title={t(keys.users.profile.sign_out_confirm_title)}
        description={t(keys.users.profile.sign_out_confirm_body)}
        confirmLabel={t(keys.users.profile.sign_out_confirm_action)}
        cancelLabel={t(keys.users.common.cancel)}
        busy={busy}
        onConfirm={revokeAll}
      />
    </Card>
  );
}
