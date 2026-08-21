import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';

interface Props {
  token: string;
}

type VerifyStatus = 'pending' | 'success' | 'already_verified' | 'error';

function VerifyEmail() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const urlToken =
    typeof window !== 'undefined'
      ? (new URLSearchParams(window.location.search).get('token') ?? '')
      : '';
  const token = urlToken || initialToken;

  const [status, setStatus] = useState<VerifyStatus>('pending');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setErrorMsg(t(keys.users.verify_email.error_no_token));
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
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : '';
          if (detail === 'VERIFY_USER_ALREADY_VERIFIED') {
            setStatus('already_verified');
          } else {
            setStatus('error');
            setErrorMsg(t(keys.users.verify_email.error_expired));
          }
        }
      })
      .catch(() => {
        setStatus('error');
        setErrorMsg(t(keys.users.common.error_try_again));
      });
  }, [token, t]);

  const loginButton = (
    <a href={LOGIN_PATH}>
      <Button className="w-full">{t(keys.users.common.log_in)}</Button>
    </a>
  );

  const content = {
    pending: {
      icon: Loader2,
      iconClass: 'text-muted-foreground animate-spin',
      title: t(keys.users.verify_email.pending_title),
      description: t(keys.users.verify_email.pending_description),
      body: null,
    },
    success: {
      icon: CheckCircle2,
      iconClass: 'text-primary-700',
      title: t(keys.users.verify_email.success_title),
      description: t(keys.users.verify_email.success_description),
      body: loginButton,
    },
    already_verified: {
      icon: CheckCircle2,
      iconClass: 'text-primary-700',
      title: t(keys.users.verify_email.already_title),
      description: t(keys.users.verify_email.already_description),
      body: loginButton,
    },
    error: {
      icon: XCircle,
      iconClass: 'text-destructive',
      title: t(keys.users.verify_email.error_title),
      description: errorMsg || t(keys.users.verify_email.error_description),
      body: (
        <a
          href={LOGIN_PATH}
          className="text-center text-sm font-semibold text-primary-700 hover:text-primary-800"
        >
          {t(keys.users.common.back_to_login)}
        </a>
      ),
    },
  }[status];

  const Icon = content.icon;

  return (
    <AuthCardShell>
      <Head title={t(keys.users.verify_email.head_title)} />
      <div className="flex flex-col items-center gap-3 text-center">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
          <Icon className={`h-6 w-6 ${content.iconClass}`} aria-hidden="true" />
        </span>
        <h1 className="text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
          {content.title}
        </h1>
        <p className="text-sm text-muted-foreground">{content.description}</p>
        {content.body && <div className="mt-2 w-full">{content.body}</div>}
      </div>
    </AuthCardShell>
  );
}

export default VerifyEmail;
