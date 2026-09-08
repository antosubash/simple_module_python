import { keys, useT } from '@simple-module-py/i18n';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';

interface InviteSummaryProps {
  email: string;
  roles: string[];
  /** ISO timestamp from the token's `exp`, or null when it carried none. */
  expiresAt: string | null;
}

/**
 * Email, role and expiry — the three facts the invite fixes.
 *
 * They used to be a green banner with the address in the sentence and the
 * roles as loose pills, which read as reassurance rather than as terms. A
 * key/value card says what is being agreed to before the password is typed,
 * and makes an invite addressed to the wrong person obvious.
 */
export function InviteSummary({ email, roles, expiresAt }: InviteSummaryProps) {
  const { t } = useT();
  const { until } = useRelativeTime();

  return (
    <dl className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
        <dt className="text-muted-foreground">{t(keys.users.accept_invite.summary_email)}</dt>
        <dd className="truncate font-mono text-[13px] text-foreground">{email}</dd>
      </div>
      {roles.length > 0 && (
        <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
          <dt className="text-muted-foreground">{t(keys.users.accept_invite.summary_role)}</dt>
          <dd className="flex flex-wrap justify-end gap-1.5">
            {roles.map((role) => (
              <span
                key={role}
                className="rounded-full bg-primary-600/10 px-2.5 py-0.5 text-[12px] font-medium text-primary-700"
              >
                {role}
              </span>
            ))}
          </dd>
        </div>
      )}
      {expiresAt && (
        <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
          <dt className="text-muted-foreground">{t(keys.users.accept_invite.summary_expires)}</dt>
          <dd className="text-foreground">{until(expiresAt)}</dd>
        </div>
      )}
    </dl>
  );
}
