import { usePage } from '@inertiajs/react';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { AuthCardShell } from '@simple-module/ui/layouts/AuthCardShell';
import { useEffect, useState } from 'react';

interface Props {
  token: string;
}

type VerifyStatus = 'pending' | 'success' | 'already_verified' | 'error';

function VerifyEmail() {
  const { token: initialToken } = usePage<{ props: Props }>().props as unknown as Props;
  const urlToken =
    typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('token') ?? ''
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
    }).then(async (res) => {
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
    }).catch(() => {
      setStatus('error');
      setErrorMsg('An error occurred. Please try again.');
    });
  }, [token]);

  const content = {
    pending: {
      title: 'Verifying your email…',
      description: 'Please wait while we verify your email address.',
      body: null,
    },
    success: {
      title: 'Email verified!',
      description: 'Your account is now active. You can sign in.',
      body: (
        <a href="/users/login">
          <Button className="w-full">Sign in</Button>
        </a>
      ),
    },
    already_verified: {
      title: 'Already verified',
      description: 'This account is already verified — you can log in.',
      body: (
        <a href="/users/login">
          <Button className="w-full">Sign in</Button>
        </a>
      ),
    },
    error: {
      title: 'Verification failed',
      description: errorMsg || 'Verification link expired or invalid.',
      body: (
        <a href="/users/login" className="text-sm text-primary hover:underline">
          Back to sign in
        </a>
      ),
    },
  }[status];

  return (
    <AuthCardShell>
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>{content.title}</CardTitle>
          <CardDescription>{content.description}</CardDescription>
        </CardHeader>
        {content.body && <CardContent>{content.body}</CardContent>}
      </Card>
    </AuthCardShell>
  );
}

export default VerifyEmail;
