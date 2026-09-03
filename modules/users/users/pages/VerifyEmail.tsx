import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { CheckCircle2, Loader2, TimerOff } from 'lucide-react';
import { useEffect, useState } from 'react';
import { AuthStateCard, type AuthStateTone } from '../auth_local/components/AuthStateCard';
import { ResendVerification } from '../auth_local/components/ResendVerification';

interface Props {
  token: string;
  /** Read off the token even when it has expired, so resend needs no retyping. */
  email: string | null;
  verification_lifetime_hours: number;
}

type VerifyStatus = 'pending' | 'success' | 'already_verified' | 'expired';

function VerifyEmail() {
  const {
    token,
    email,
    verification_lifetime_hours: lifetimeHours,
  } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const [status, setStatus] = useState<VerifyStatus>('pending');

  useEffect(() => {
    if (!token) {
      setStatus('expired');
      return;
    }

    fetch('/api/users/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (res.status === 200 || res.status === 204) {
          setStatus('success');
          return;
        }
        const data = await res.json().catch(() => ({}));
        const detail = typeof data?.detail === 'string' ? data.detail : '';
        setStatus(detail === 'VERIFY_USER_ALREADY_VERIFIED' ? 'already_verified' : 'expired');
      })
      .catch(() => setStatus('expired'));
  }, [token]);

  const signInButton = (
    <Button asChild className="max-lg:min-h-11">
      <a href={LOGIN_PATH}>{t(keys.users.verify_email.success_action)}</a>
    </Button>
  );

  interface StateCard {
    icon: typeof CheckCircle2;
    iconClassName?: string;
    tone: AuthStateTone;
    title: string;
    description: string;
    body: React.ReactNode;
  }

  const cards: Record<VerifyStatus, StateCard> = {
    pending: {
      icon: Loader2,
      iconClassName: 'animate-spin',
      tone: 'neutral',
      title: t(keys.users.verify_email.pending_title),
      description: t(keys.users.verify_email.pending_description),
      body: null,
    },
    success: {
      icon: CheckCircle2,
      tone: 'primary',
      title: t(keys.users.verify_email.success_title),
      description: t(keys.users.verify_email.success_description),
      body: signInButton,
    },
    already_verified: {
      icon: CheckCircle2,
      tone: 'primary',
      title: t(keys.users.verify_email.already_title),
      description: t(keys.users.verify_email.already_description),
      body: signInButton,
    },
    expired: {
      icon: TimerOff,
      tone: 'amber',
      title: t(keys.users.verify_email.expired_title),
      description: t(keys.users.verify_email.expired_description, { hours: lifetimeHours }),
      body: <ResendVerification email={email} />,
    },
  };
  const card = cards[status];

  return (
    <AuthCardShell>
      <Head title={t(keys.users.verify_email.head_title)} />
      <AuthStateCard
        icon={card.icon}
        iconClassName={card.iconClassName}
        tone={card.tone}
        title={card.title}
        description={card.description}
      >
        {card.body}
      </AuthStateCard>
    </AuthCardShell>
  );
}

export default VerifyEmail;
