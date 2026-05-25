import { Head, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { useState } from 'react';
import { toast } from 'sonner';

interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  is_verified: boolean;
  roles: string[];
}

interface SharedProps {
  auth: {
    user: AuthUser | null;
  };
}

function Profile() {
  const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const user = auth?.user;

  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [saving, setSaving] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    fetch('/api/users/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: fullName }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('Profile updated');
        } else {
          const data = await res.json().catch(() => ({}));
          toast.error(typeof data?.detail === 'string' ? data.detail : 'Failed to update profile');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSaving(false));
  };

  if (!user) {
    return null;
  }

  const initial = (user.full_name || user.email).charAt(0).toUpperCase();

  return (
    <>
      <Head title="Profile" />
      <PageShell title="Your profile" description="Shown to teammates in audit logs and dropdowns.">
        <Card className="max-w-2xl border-border">
          <CardContent className="pt-6">
            <SectionTitle>Account</SectionTitle>
            <div className="mb-5 flex items-center gap-4">
              <span className="inline-flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-primary-600 to-primary-800 text-2xl font-bold text-white shadow-md font-[var(--font-display)]">
                {initial}
              </span>
              <div>
                <Button type="button" size="sm" variant="outline">
                  Upload avatar
                </Button>
                <div className="mt-1.5 text-xs text-muted-foreground">PNG or JPG, up to 2MB.</div>
              </div>
            </div>
            <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="email" className="text-sm font-medium text-muted-foreground">
                  Email
                </Label>
                <div className="flex items-center gap-2">
                  <Input
                    id="email"
                    type="email"
                    value={user.email}
                    readOnly
                    className="bg-muted flex-1"
                  />
                  {user.is_verified ? (
                    <Badge
                      variant="outline"
                      className="border-primary-200 bg-primary-50 text-primary-700"
                    >
                      verified
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="border-amber-200 bg-amber-50 text-amber-700"
                    >
                      unverified
                    </Badge>
                  )}
                </div>
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="full_name" className="text-sm font-medium text-muted-foreground">
                  Display name
                </Label>
                <Input
                  id="full_name"
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Your name"
                  maxLength={200}
                />
              </div>

              {user.roles.length > 0 && (
                <div className="space-y-1.5 sm:col-span-2">
                  <Label className="text-sm font-medium text-muted-foreground">Roles</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {user.roles.map((role) => (
                      <Badge
                        key={role}
                        variant="outline"
                        className="border-primary-200 bg-primary-50 text-primary-700"
                      >
                        {role}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <div className="sm:col-span-2 flex justify-end">
                <Button type="submit" disabled={saving}>
                  {saving ? 'Saving…' : 'Save changes'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </PageShell>
    </>
  );
}

Profile.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Profile;
