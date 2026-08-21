import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { TabsContent } from '@simple-module-py/ui/components/ui/tabs';
import { Pencil, ShieldCheck, Users } from 'lucide-react';

export interface RoleItem {
  id: string;
  name: string;
  description?: string | null;
  user_count: number;
}

const SYSTEM_ROLES = new Set(['Owner', 'Admin', 'Viewer']);

export function RolesTab({ roles }: { roles: RoleItem[] }) {
  const { t } = useT();
  return (
    <TabsContent value="roles">
      {roles.length === 0 ? (
        <Card className="border-border">
          <CardContent className="flex flex-col items-center gap-2 py-16 text-muted-foreground">
            <ShieldCheck className="size-8" />
            <p>{t(keys.users.roles_tab.empty)}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {roles.map((role) => {
            const isSystem = SYSTEM_ROLES.has(role.name);
            return (
              <Card key={role.id} className="border-border">
                <CardContent className="pt-5">
                  <div className="flex items-start gap-3">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700">
                      {isSystem ? (
                        <ShieldCheck className="h-[18px] w-[18px]" aria-hidden="true" />
                      ) : (
                        <Users className="h-[18px] w-[18px]" aria-hidden="true" />
                      )}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-[15px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
                          {role.name}
                        </h3>
                        {isSystem && (
                          <Badge
                            variant="outline"
                            className="border-border bg-secondary text-[10px] text-muted-foreground"
                          >
                            {t(keys.users.roles_tab.system_badge)}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                        {role.description || t(keys.users.roles_tab.no_description)}
                      </p>
                      <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                        {t(keys.users.roles_tab.member_count, { count: role.user_count })}
                      </div>
                    </div>
                    <Button asChild variant="ghost" size="icon-sm">
                      <Link
                        href={`/permissions/roles/${role.id}/edit`}
                        aria-label={t(keys.users.roles_tab.edit_role)}
                      >
                        <Pencil />
                      </Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </TabsContent>
  );
}
