import { keys, useT } from '@simple-module-py/i18n';
import { Mail } from 'lucide-react';
import { useEffect, useState } from 'react';
import { AuthStateCard } from './AuthStateCard';

/** Seconds before the link can be asked for again.
 *
 * The auth side-effect limiter allows ten attempts per five minutes — one
 * every thirty seconds — so a shorter wait would hand out 429s instead of
 * emails. A minute keeps a double-click well clear of the budget. */
const RESEND_AFTER_SECONDS = 60;

interface ResetLinkSentProps {
  email: string;
  /** False when the configured mailer only logs — the amber callout then shows. */
  mailerDelivers: boolean;
  /** Resolves true when the server accepted the request, false when it did not. */
  onResend: () => Promise<boolean>;
}

function formatCountdown(seconds: number): string {
  const rest = seconds % 60;
  return `${Math.floor(seconds / 60)}:${rest.toString().padStart(2, '0')}`;
}

/**
 * "Check your inbox" — the same answer whether or not the address exists.
 *
 * The address is repeated in bold because this screen is the only chance to
 * notice a typo: no email will arrive, and nothing else will say why. The
 * console-mailer callout appears only when the mailer genuinely cannot
 * deliver, so a real SMTP install is not told to go and read a log.
 */
export function ResetLinkSent({ email, mailerDelivers, onResend }: ResetLinkSentProps) {
  const { t } = useT();
  const [remaining, setRemaining] = useState(RESEND_AFTER_SECONDS);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (remaining <= 0) return;
    const timer = setTimeout(() => setRemaining((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [remaining]);

  const handleResend = () => {
    setFailed(false);
    // Only restart the countdown once the server has actually taken it. A
    // refusal (the throughput limiter answers 429) that silently reset the
    // timer would read as "sent again" and leave someone waiting a minute for
    // nothing.
    onResend().then((accepted) => {
      if (accepted) {
        setRemaining(RESEND_AFTER_SECONDS);
      } else {
        setFailed(true);
      }
    });
  };

  return (
    <AuthStateCard
      icon={Mail}
      tone="primary"
      title={t(keys.users.forgot_password.sent_title)}
      description={
        <>
          {t(keys.users.forgot_password.sent_body_prefix)}{' '}
          <b className="font-semibold text-foreground">{email}</b>
          {t(keys.users.forgot_password.sent_body_suffix)}
        </>
      }
    >
      {!mailerDelivers && (
        <p className="w-full rounded-[10px] border border-amber-200 bg-amber-50 px-3.5 py-3 text-[12.5px] leading-relaxed text-amber-700">
          {t(keys.users.forgot_password.console_mailer_note)}
        </p>
      )}
      {failed && (
        <p className="text-[13px] text-destructive">
          {t(keys.users.forgot_password.resend_failed)}
        </p>
      )}
      <button
        type="button"
        onClick={handleResend}
        disabled={remaining > 0}
        className="text-[13px] font-medium text-primary-700 hover:text-primary-800 disabled:text-muted-foreground disabled:hover:text-muted-foreground"
      >
        {remaining > 0
          ? t(keys.users.forgot_password.resend_in, { countdown: formatCountdown(remaining) })
          : t(keys.users.forgot_password.resend)}
      </button>
    </AuthStateCard>
  );
}
