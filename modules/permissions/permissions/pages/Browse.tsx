import { keys, useT } from '@simple-module/i18n';

type Group = { name: string; permissions: string[] };
type Role = {
  id: string;
  name: string;
  description: string | null;
  permission_count: number;
};

type Props = { groups: Group[]; roles: Role[] };

export default function Browse({ groups, roles }: Props) {
  const { t } = useT();
  return (
    <div className="p-6 space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">{t(keys.permissions.browse.title)}</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {t(keys.permissions.browse.description)}
        </p>
      </div>

      <section>
        <h2 className="text-lg font-medium mb-3">{t(keys.permissions.browse.roles_heading)}</h2>
        {roles.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(keys.permissions.browse.no_roles)}</p>
        ) : (
          <ul className="divide-y border rounded">
            {roles.map((role) => (
              <li key={role.id} className="py-2 px-3 flex justify-between items-center">
                <div>
                  <div className="font-medium">{role.name}</div>
                  {role.description && (
                    <div className="text-xs text-muted-foreground">{role.description}</div>
                  )}
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-muted-foreground">
                    {t(keys.permissions.browse.count_label, {
                      count: role.permission_count,
                    })}
                  </span>
                  <a href={`/permissions/roles/${role.id}/edit`} className="text-sm underline">
                    {t(keys.permissions.browse.edit_link)}
                  </a>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="text-lg font-medium mb-3">{t(keys.permissions.browse.registry_heading)}</h2>
        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {t(keys.permissions.browse.no_permissions)}
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {groups.map((group) => (
              <div key={group.name} className="border rounded p-3">
                <div className="font-medium mb-2">{group.name}</div>
                <ul className="space-y-1">
                  {group.permissions.map((key) => (
                    <li key={key} className="text-sm font-mono">
                      {key}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
