import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent } from '@simple-module/ui/components/ui/card';
import { Checkbox } from '@simple-module/ui/components/ui/checkbox';
import { Input } from '@simple-module/ui/components/ui/input';
import { Label } from '@simple-module/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { useState } from 'react';
import { toast } from 'sonner';

interface Role {
  id: string;
  name: string;
}

interface Props {
  roles: Role[];
}

function Invite() {
  const { roles } = usePage<{ props: Props }>().props as unknown as Props;

  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    fetch('/api/users/admin/invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, full_name: fullName || null, roles: selectedRoles }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('Invite sent');
          router.visit('/users/admin');
        } else {
          const data = await res.json().catch(() => ({}));
          setError(typeof data?.detail === 'string' ? data.detail : 'Failed to send invite');
        }
      })
      .catch(() => setError('An error occurred. Please try again.'))
      .finally(() => setLoading(false));
  };

  return (
    <PageShell
      title="Invite user"
      description="Send an invitation email to a new user"
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">Back to Users</Link>
        </Button>
      }
    >
      <Card className="max-w-xl">
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email">
                Email <span className="text-destructive">*</span>
              </Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="user@example.com"
                required
                autoComplete="off"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="full_name">Full name</Label>
              <Input
                id="full_name"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Optional"
              />
            </div>

            {roles.length > 0 && (
              <div className="space-y-2">
                <Label>Roles</Label>
                <div className="flex flex-col gap-2">
                  {roles.map((role) => (
                    <div key={role.id} className="flex items-center gap-2">
                      <Checkbox
                        id={`role-${role.id}`}
                        checked={selectedRoles.includes(role.name)}
                        onCheckedChange={() => toggleRole(role.name)}
                      />
                      <Label htmlFor={`role-${role.id}`} className="cursor-pointer font-normal">
                        {role.name}
                      </Label>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="pt-2 flex gap-3">
              <Button type="submit" disabled={loading}>
                {loading ? 'Sending…' : 'Send invite'}
              </Button>
              <Button asChild variant="outline">
                <Link href="/users/admin">Cancel</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </PageShell>
  );
}

Invite.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Invite;
