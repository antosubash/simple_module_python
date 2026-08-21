import { Link } from '@inertiajs/react';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { ShieldCheck } from 'lucide-react';
import { type Role, RolePicker } from './RolePicker';

interface Props {
  roles: Role[];
  selected: string[];
  onToggle: (roleName: string) => void;
  userId: string;
  hasPermissionsModule: boolean;
}

/**
 * Role assignment. Has no save button of its own — roles are part of the
 * page's single dirty state, saved with everything else.
 */
export function RolesCard({ roles, selected, onToggle, userId, hasPermissionsModule }: Props) {
  return (
    <Card className="border-border lg:col-span-2">
      <CardContent className="pt-5">
        <SectionTitle>Roles</SectionTitle>
        <RolePicker roles={roles} selected={selected} onToggle={onToggle} label="" />
        {hasPermissionsModule && (
          <Link
            href={`/admin/permissions/users/${userId}/edit`}
            className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-primary-700 hover:text-primary-800"
          >
            <ShieldCheck className="size-4" />
            Manage permissions →
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
