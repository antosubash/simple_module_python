import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';

export interface DemoAccount {
  /** `admin` or `user` — also the last segment of the sign-in route. */
  role: string;
}

interface DemoSignInProps {
  accounts: DemoAccount[];
  /** Whether the demo session will be refused every write. */
  readOnly: boolean;
  /** Role currently being signed in, or `null`. */
  pendingRole: string | null;
  error: string | null;
  onStart: (role: string) => void;
}

/**
 * Copy per role. `as const` is load-bearing: `t()` accepts only keys present
 * in the generated union, so a widened `Record<string, string>` would not
 * typecheck — which is the catalog guarantee working, not an obstacle.
 */
const ROLE_COPY = {
  admin: { label: keys.users.login.demo_admin, hint: keys.users.login.demo_admin_hint },
  user: { label: keys.users.login.demo_user, hint: keys.users.login.demo_user_hint },
} as const;

type RoleCopy = (typeof ROLE_COPY)[keyof typeof ROLE_COPY];

function copyFor(role: string): RoleCopy | undefined {
  return ROLE_COPY[role as keyof typeof ROLE_COPY];
}

/**
 * The demo entry — one button per configured account.
 *
 * Deliberately below the credentials form and behind its own divider: these
 * are alternatives to signing in, not OAuth providers, and putting them in
 * that row would read as "sign in with Demo".
 *
 * No email or password crosses the wire. Each button posts to
 * `/api/users/auth/demo/{role}`, which looks the shared account up
 * server-side — the dev quick-fill buttons below paste real credentials into
 * the form and are development-only for exactly that reason.
 *
 * A role with no label key still renders, captioned by its own name: a demo
 * account the server offers must never be unreachable because this map is
 * behind.
 */
export function DemoSignIn({ accounts, readOnly, pendingRole, error, onStart }: DemoSignInProps) {
  const { t } = useT();
  const busy = pendingRole !== null;

  return (
    <div className="mt-5 border-t border-border pt-4">
      <p className="mb-2 text-center text-[12.5px] font-medium text-muted-foreground">
        {t(keys.users.login.demo_divider)}
      </p>
      <div className="flex flex-col gap-2">
        {accounts.map((account) => {
          const copy = copyFor(account.role);
          return (
            <Button
              key={account.role}
              type="button"
              variant="outline"
              size="lg"
              className="w-full flex-col gap-0.5 py-3 h-auto"
              disabled={busy}
              onClick={() => onStart(account.role)}
            >
              <span className="font-medium">
                {pendingRole === account.role
                  ? t(keys.users.login.demo_submitting)
                  : copy
                    ? t(copy.label)
                    : account.role}
              </span>
              {copy && (
                <span className="text-[12px] font-normal text-muted-foreground">
                  {t(copy.hint)}
                </span>
              )}
            </Button>
          );
        })}
      </div>
      <p className="mt-2 text-center text-[12.5px] text-muted-foreground">
        {readOnly
          ? t(keys.users.login.demo_hint_read_only)
          : t(keys.users.login.demo_hint_writable)}
      </p>
      {error && <p className="mt-2 text-center text-sm text-destructive">{error}</p>}
    </div>
  );
}
