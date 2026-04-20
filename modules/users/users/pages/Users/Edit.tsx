import { Link, router, usePage } from '@inertiajs/react';
import { PageShell } from '@simple-module/ui/components/PageShell';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@simple-module/ui/components/ui/alert-dialog';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module/ui/components/ui/card';
import { Checkbox } from '@simple-module/ui/components/ui/checkbox';
import { Label } from '@simple-module/ui/components/ui/label';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  disabled_at: string | null;
  last_login_at: string | null;
  created_at: string | null;
  roles: string[];
}

interface Role {
  id: string;
  name: string;
}

interface Props {
  user: UserListItem;
  roles: Role[];
  has_permissions_module: boolean;
}

function fmt(dt: string | null): string {
  if (!dt) return '—';
  return new Date(dt).toLocaleString();
}

function Edit() {
  const { user, roles, has_permissions_module } = usePage<{ props: Props }>()
    .props as unknown as Props;

  const [isActive, setIsActive] = useState(user.is_active);
  const [isVerified, setIsVerified] = useState(user.is_verified);
  const [selectedRoles, setSelectedRoles] = useState<string[]>(user.roles ?? []);
  const [savingStatus, setSavingStatus] = useState(false);
  const [savingRoles, setSavingRoles] = useState(false);
  const [savingVerify, setSavingVerify] = useState(false);

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );
  };

  const disableAccount = () => {
    setSavingStatus(true);
    fetch(`/api/users/admin/${user.id}/disable`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsActive(false);
          toast.success('User disabled');
        } else {
          toast.error('Failed to disable user');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingStatus(false));
  };

  const enableAccount = () => {
    setSavingStatus(true);
    fetch(`/api/users/admin/${user.id}/enable`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsActive(true);
          toast.success('User enabled');
        } else {
          toast.error('Failed to enable user');
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
          toast.error('Failed to update roles');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingRoles(false));
  };

  const copyResetLink = () => {
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

  const markVerified = () => {
    setSavingVerify(true);
    fetch(`/api/users/admin/${user.id}/verify`, { method: 'PATCH' })
      .then(async (res) => {
        if (res.ok) {
          setIsVerified(true);
          toast.success('User marked verified');
        } else {
          toast.error('Failed to mark verified');
        }
      })
      .catch(() => toast.error('An error occurred'))
      .finally(() => setSavingVerify(false));
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
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Metadata</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
            <span className="text-muted-foreground">Created</span>
            <span>{fmt(user.created_at)}</span>
            <span className="text-muted-foreground">Last login</span>
            <span>{user.last_login_at ? fmt(user.last_login_at) : 'Never'}</span>
            <span className="text-muted-foreground">Disabled at</span>
            <span>{fmt(user.disabled_at)}</span>
            <span className="text-muted-foreground">Verified</span>
            <span className="flex items-center gap-2">
              {isVerified ? (
                'Yes'
              ) : (
                <>
                  No
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={markVerified}
                    disabled={savingVerify}
                  >
                    {savingVerify ? 'Saving…' : 'Mark verified'}
                  </Button>
                </>
              )}
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Account status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge variant={isActive ? 'secondary' : 'destructive'}>
                {isActive ? 'Active' : 'Disabled'}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              {isActive ? (
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive" size="sm" disabled={savingStatus}>
                      {savingStatus ? 'Saving…' : 'Disable account'}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Disable {user.email}?</AlertDialogTitle>
                      <AlertDialogDescription>
                        They won't be able to sign in until you re-enable the account.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={disableAccount}>Disable</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              ) : (
                <Button size="sm" onClick={enableAccount} disabled={savingStatus}>
                  {savingStatus ? 'Saving…' : 'Enable account'}
                </Button>
              )}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" size="sm">
                    Copy reset-password link
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Generate reset link for {user.email}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      A one-time password-reset URL will be copied to your clipboard.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={copyResetLink}>Generate</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </CardContent>
        </Card>

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
              <Button size="sm" variant="ghost" onClick={() => router.reload()}>
                Discard
              </Button>
            </div>
          </CardContent>
        </Card>

        {has_permissions_module && (
          <Link
            href={`/permissions/users/${user.id}`}
            className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
          >
            <ShieldCheck className="size-4" />
            Manage permissions →
          </Link>
        )}
      </div>
    </PageShell>
  );
}

Edit.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Edit;
