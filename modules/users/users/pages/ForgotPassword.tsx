import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
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
    })
      .finally(() => {
        // Always show the same message regardless of whether the email exists
        // (anti-enumeration: fastapi-users returns 202 regardless)
        setLoading(false);
        setSubmitted(true);
      });
  };

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted p-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>Check your email</CardTitle>
            <CardDescription>
              If an account with that email exists, we've sent a password reset link.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <a href="/users/login" className="text-sm text-primary hover:underline">
              Back to sign in
            </a>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">Forgot password</CardTitle>
          <CardDescription>Enter your email to receive a reset link</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
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
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Sending…' : 'Send reset link'}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            <a href="/users/login" className="text-primary hover:underline">
              Back to sign in
            </a>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default ForgotPassword;
