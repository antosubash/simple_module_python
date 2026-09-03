import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Mail } from 'lucide-react';
import { AuthStateCard } from './AuthStateCard';

interface WaitingOnYouProps {
  /** The address that tried to sign in — shown so a typo is obvious. */
  email: string;
  onResend: () => void;
  onBack: () => void;
  /** Set once the resend request has gone out. */
  resent: boolean;
}

/**
 * What an unverified account gets instead of being signed in.
 *
 * This used to be an amber strip wedged into the sign-in form, which left the
 * form looking submittable when it was not. Nothing else is reachable until
 * the address is confirmed, so the card replaces the form and offers the one
 * action that moves things along.
 */
export function WaitingOnYou({ email, onResend, onBack, resent }: WaitingOnYouProps) {
  const { t } = useT();
  return (
    <AuthStateCard
      icon={Mail}
      tone="neutral"
      title={t(keys.users.login.waiting_title)}
      description={t(keys.users.login.waiting_body)}
    >
      <span className="max-w-full truncate rounded-lg bg-secondary px-3 py-2 font-mono text-[12.5px] text-muted-foreground">
        {email}
      </span>
      {resent ? (
        <p className="text-[13px] text-primary-700">{t(keys.users.login.verification_resent)}</p>
      ) : (
        <Button type="button" variant="outline" onClick={onResend} className="max-lg:min-h-11">
          {t(keys.users.login.resend_verification)}
        </Button>
      )}
      <button
        type="button"
        onClick={onBack}
        className="text-[13px] font-medium text-primary-700 hover:text-primary-800"
      >
        {t(keys.users.login.waiting_back)}
      </button>
    </AuthStateCard>
  );
}
