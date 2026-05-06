import { usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Button } from '@simple-module-py/ui/components/ui/button';
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

const SECTIONS = [
  'Profile',
  'Workspaces',
  'API tokens',
  'Notifications',
  'Sessions',
  'Danger zone',
];

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

  return (
    <PageShell title="Settings" description="Manage your account details">
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[200px_1fr]">
        <nav className="flex flex-col gap-1">
          {SECTIONS.map((s, i) => (
            <div
              key={s}
              className={
                i === 0
                  ? 'rounded border bg-secondary px-3 py-1.5 text-xs font-semibold'
                  : 'px-3 py-1.5 text-xs font-medium text-muted-foreground'
              }
            >
              {s}
            </div>
          ))}
        </nav>

        <div className="max-w-xl space-y-6">
          <div>
            <h2 className="text-lg font-semibold">Profile</h2>
            <p className="text-xs text-muted-foreground">
              Visible to your collaborators across the workspace.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full border bg-secondary" />
              <div className="space-y-1.5">
                <Button type="button" variant="outline" size="sm">
                  Upload photo
                </Button>
                <p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  PNG/JPG · 1MB max
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs font-medium">
                  Email
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={user.email}
                  readOnly
                  className="bg-muted font-mono text-sm"
                />
                <p className="font-mono text-[10px] text-muted-foreground">
                  {user.is_verified ? '✓ verified' : '× unverified'}
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="full_name" className="text-xs font-medium">
                  Full name
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
            </div>

            {user.roles.length > 0 && (
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">Roles</Label>
                <div className="flex flex-wrap gap-1.5">
                  {user.roles.map((role) => (
                    <span
                      key={role}
                      className="inline-flex items-center rounded-full border bg-secondary px-2 py-0.5 font-mono text-[11px] text-muted-foreground"
                    >
                      {role}
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <Button type="button" variant="outline" disabled={saving}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving ? 'Saving…' : 'Save changes'}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </PageShell>
  );
}

Profile.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Profile;
