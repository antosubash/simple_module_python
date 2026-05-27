import { Head } from '@inertiajs/react';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    fetch('/api/users/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    }).finally(() => {
      // Anti-enumeration: always show the same confirmation regardless of
      // whether the email exists (fastapi-users returns 202 either way).
      setLoading(false);
      setSubmitted(true);
    });
  };

  if (submitted) {
    return (
      <AuthCardShell>
        <div className="flex items-start gap-3 rounded-xl border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-semibold">Check your inbox</p>
            <p className="mt-0.5">
              If <strong>{email}</strong> has an account, a reset link is on its way. The console
              mailer logs it to stdout.
            </p>
          </div>
        </div>
        <a
          href="/users/login"
          className="mt-4 block text-center text-sm font-semibold text-primary-700 hover:text-primary-800"
        >
          Back to log in
        </a>
      </AuthCardShell>
    );
  }

  return (
    <AuthCardShell>
      <Head title="Forgot Password" />
      <h1 className="mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        Forgot password
      </h1>
      <p className="mb-5 text-sm text-muted-foreground">We'll email you a one-time reset link.</p>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-1.5">
          <Label htmlFor="email" className="text-sm font-medium text-muted-foreground">
            Email
          </Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            required
            autoComplete="email"
          />
        </div>
        <Button type="submit" size="lg" className="w-full" disabled={loading}>
          {loading ? 'Sending…' : 'Send reset link'}
        </Button>
      </form>
      <p className="mt-5 text-center text-xs text-muted-foreground">
        Remembered?{' '}
        <a href="/users/login" className="font-semibold text-primary-700 hover:text-primary-800">
          Log in
        </a>
      </p>
    </AuthCardShell>
  );
}

export default ForgotPassword;
