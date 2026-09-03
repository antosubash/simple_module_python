import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { useState } from 'react';

interface ResendVerificationProps {
  /** Decoded from the dead token. Null when it could not be read at all. */
  email: string | null;
}

/**
 * "Send me another one."
 *
 * The address comes off the expired token server-side, so the common case is
 * a single button — nobody should have to retype an address they already gave
 * to get past a link that timed out. When the token was too mangled to read,
 * the field appears instead of the screen simply being a dead end. The
 * endpoint answers the same way either way, so nothing here leaks whether an
 * account exists.
 */
export function ResendVerification({ email }: ResendVerificationProps) {
  const { t } = useT();
  const [typed, setTyped] = useState('');
  const [sent, setSent] = useState(false);

  const address = email ?? typed;

  const resend = () => {
    fetch('/api/users/auth/request-verify-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: address }),
    }).then(() => setSent(true));
  };

  if (sent) {
    return <p className="text-[13px] text-primary-700">{t(keys.users.verify_email.resent)}</p>;
  }

  return (
    <div className="flex w-full flex-col gap-3">
      {email === null && (
        <Input
          type="email"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={t(keys.users.common.email_placeholder)}
          autoComplete="email"
          aria-label={t(keys.users.common.email)}
        />
      )}
      <Button
        type="button"
        variant="outline"
        onClick={resend}
        disabled={!address}
        className="self-start max-lg:min-h-11"
      >
        {t(keys.users.verify_email.resend)}
      </Button>
    </div>
  );
}
