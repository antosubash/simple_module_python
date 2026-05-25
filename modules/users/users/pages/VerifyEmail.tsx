import { Head, usePage } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { CheckCircle2, Loader2, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';

interface Props {
  token: string;
}

type VerifyStatus = 'pending' | 'success' | 'already_verified' | 'error';

function VerifyEmail() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;
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
      setErrorMsg('No verification token found in this link.');
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
            setErrorMsg('Verification link expired or invalid. Please request a new one.');
          }
        }
      })
      .catch(() => {
        setStatus('error');
        setErrorMsg('An error occurred. Please try again.');
      });
  }, [token]);

  const content = {
    pending: {
      icon: Loader2,
      iconClass: 'text-muted-foreground animate-spin',
      title: 'Verifying your email…',
      description: 'Please wait while we verify your email address.',
      body: null,
    },
    success: {
      icon: CheckCircle2,
      iconClass: 'text-primary-700',
      title: 'Email verified!',
      description: 'Your account is now active.',
      body: (
        <a href="/users/login">
          <Button className="w-full">Log in</Button>
        </a>
      ),
    },
    already_verified: {
      icon: CheckCircle2,
      iconClass: 'text-primary-700',
      title: 'Already verified',
      description: 'This account is already verified — you can log in.',
      body: (
        <a href="/users/login">
          <Button className="w-full">Log in</Button>
        </a>
      ),
    },
    error: {
      icon: XCircle,
      iconClass: 'text-destructive',
      title: 'Verification failed',
      description: errorMsg || 'Verification link expired or invalid.',
      body: (
        <a
          href="/users/login"
          className="text-center text-sm font-semibold text-primary-700 hover:text-primary-800"
        >
          Back to log in
        </a>
      ),
    },
  }[status];

  const Icon = content.icon;

  return (
    <AuthCardShell>
      <Head title="Verify Email" />
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
