import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Checkbox } from '@simple-module/ui/components/ui/checkbox';
import { Label } from '@simple-module/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { useState } from 'react';
import { toast } from 'sonner';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  last_login_at: string | null;
  roles: string[];
}

interface Role {
  id: string;
  name: string;
}

interface Props {
  user: UserListItem;
  roles: Role[];
}

function Edit() {
  const { user, roles } = usePage<{ props: Props }>().props as unknown as Props;

  const [isActive, setIsActive] = useState(user.is_active);
  const [selectedRoles, setSelectedRoles] = useState<string[]>(user.roles ?? []);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingRoles, setSavingRoles] = useState(false);

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );
  };

  const handleToggleActive = () => {
    setSavingStatus(true);
    const endpoint = isActive
      ? `/api/users/admin/${user.id}/disable`
      : `/api/users/admin/${user.id}/enable`;
    fetch(endpoint, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          const newActive = !isActive;
          setIsActive(newActive);
          toast.success(newActive ? 'User enabled' : 'User disabled');
        } else {
          const data = await res.json().catch(() => ({}));
          toast.error(typeof data?.detail === 'string' ? data.detail : 'Failed to update status');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingStatus(false));
  };

  const handleSaveRoles = () => {
    setSavingRoles(true);
    fetch(`/api/users/admin/${user.id}/roles`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role_names: selectedRoles }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success('Roles updated');
        } else {
          const data = await res.json().catch(() => ({}));
          toast.error(typeof data?.detail === 'string' ? data.detail : 'Failed to update roles');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingRoles(false));
  };

  const handleCopyResetLink = () => {
    fetch(`/api/users/admin/${user.id}/reset-password-link`, { method: 'POST' })
      .then(async (res) => {
        if (res.ok) {
          const data = await res.json();
          await navigator.clipboard.writeText(data.link ?? data.url ?? '');
          toast.success('Reset link copied to clipboard');
        } else {
          toast.error('Failed to generate reset link');
        }
      })
      .catch(() => toast.error('An error occurred'));
  };

  const handleReload = () => {
    router.reload();
  };

  return (
    <PageShell
      title={user.email}
      description={user.full_name ?? 'Edit user account'}
      actions={
        <Button asChild variant="outline">
          <Link href="/users/admin">Back to Users</Link>
        </Button>
      }
    >
      <div className="space-y-6 max-w-xl">
        {/* Status card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Account status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge variant={isActive ? 'secondary' : 'destructive'}>
                {isActive ? 'Active' : 'Disabled'}
              </Badge>
              {user.is_verified ? (
                <Badge variant="outline">Verified</Badge>
              ) : (
                <Badge variant="outline" className="text-amber-600 border-amber-300">
                  Unverified
                </Badge>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={isActive ? 'destructive' : 'default'}
                size="sm"
                onClick={handleToggleActive}
                disabled={savingStatus}
              >
                {savingStatus ? 'Saving…' : isActive ? 'Disable account' : 'Enable account'}
              </Button>
              <Button variant="outline" size="sm" onClick={handleCopyResetLink}>
                Copy reset-password link
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Roles card */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Roles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveRoles} disabled={savingRoles}>
                {savingRoles ? 'Saving…' : 'Save roles'}
              </Button>
              <Button size="sm" variant="ghost" onClick={handleReload}>
                Discard
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
