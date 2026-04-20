import { Link } from '@inertiajs/react';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card } from '@simple-module/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module/ui/components/ui/table';
import { TabsContent } from '@simple-module/ui/components/ui/tabs';
import { Pencil, ShieldCheck } from 'lucide-react';

export interface RoleItem {
  id: string;
  name: string;
  description?: string | null;
}

export function RolesTab({ roles }: { roles: RoleItem[] }) {
  return (
    <TabsContent value="roles">
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Role</TableHead>
              <TableHead className="hidden md:table-cell">Description</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {roles.map((role) => (
              <TableRow key={role.id}>
                <TableCell className="font-medium">{role.name}</TableCell>
                <TableCell className="hidden md:table-cell text-muted-foreground text-sm">
                  {role.description || '—'}
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild variant="ghost" size="icon-sm">
                    <Link href={`/permissions/roles/${role.id}/edit`} aria-label="Edit role">
                      <Pencil />
                    </Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {roles.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="h-32 text-center">
                  <div className="flex flex-col items-center gap-2 text-muted-foreground">
                    <ShieldCheck className="size-8" />
                    <p>No roles defined</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </TabsContent>
  );
}
