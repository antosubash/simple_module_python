import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';

interface DemoSignInProps {
  /** Whether the demo session will be refused every write. */
  readOnly: boolean;
  pending: boolean;
  error: string | null;
  onStart: () => void;
}

/**
 * "Explore the demo" — the one-click entry to a showcase instance.
 *
 * Deliberately below the credentials form and behind its own divider: it is an
 * alternative to signing in, not an OAuth provider, and putting it in that row
 * would read as "sign in with Demo".
 *
 * No email or password crosses the wire. The button posts to
 * `/api/users/auth/demo`, which looks the shared account up server-side — the
 * dev quick-fill buttons above it paste real credentials into the form and are
 * development-only for exactly that reason.
 */
export function DemoSignIn({ readOnly, pending, error, onStart }: DemoSignInProps) {
  const { t } = useT();

  return (
    <div className="mt-5 border-t border-border pt-4">
      <p className="mb-2 text-center text-[12.5px] font-medium text-muted-foreground">
        {t(keys.users.login.demo_divider)}
      </p>
      <Button
        type="button"
        variant="outline"
        size="lg"
        className="w-full"
        disabled={pending}
        onClick={onStart}
      >
        {pending ? t(keys.users.login.demo_submitting) : t(keys.users.login.demo_submit)}
      </Button>
      <p className="mt-2 text-center text-[12.5px] text-muted-foreground">
        {readOnly
          ? t(keys.users.login.demo_hint_read_only)
          : t(keys.users.login.demo_hint_writable)}
      </p>
      {error && <p className="mt-2 text-center text-sm text-destructive">{error}</p>}
    </div>
  );
}
