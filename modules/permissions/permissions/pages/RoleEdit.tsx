import { keys, useT } from '@simple-module/i18n';

type Group = { name: string; permissions: string[] };
type Role = { id: string; name: string; description: string | null };

type Props = { role: Role; assigned: string[]; groups: Group[] };

export default function RoleEdit({ role, assigned, groups }: Props) {
  const { t } = useT();
  const assignedSet = new Set(assigned);

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">
        {t(keys.permissions.edit.title, { role: role.name })}
      </h1>
      {role.description && <p className="text-sm text-muted-foreground mb-4">{role.description}</p>}

      <form method="post" action={`/permissions/roles/${role.id}`} className="space-y-6">
        <input type="hidden" name="_method" value="put" />

        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(keys.permissions.edit.empty)}</p>
        ) : (
          groups.map((group) => (
            <fieldset key={group.name} className="border rounded p-3">
              <legend className="px-2 font-medium">{group.name}</legend>
              <div className="space-y-1">
                {group.permissions.map((key) => (
                  <label key={key} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      name="permissions"
                      value={key}
                      defaultChecked={assignedSet.has(key)}
                    />
                    <span className="font-mono">{key}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))
        )}

        <div className="flex gap-2">
          <button type="submit" className="rounded bg-primary px-3 py-1.5 text-primary-foreground">
            {t(keys.permissions.edit.submit_button)}
          </button>
          <a href="/permissions" className="rounded border px-3 py-1.5">
            {t(keys.permissions.edit.cancel_link)}
          </a>
        </div>
      </form>
    </div>
  );
}
