import { keys, useT } from '@simple-module/i18n';

type Group = { name: string; permissions: string[] };
type User = { id: string; email: string; full_name: string | null };

type Props = {
  user: User;
  roles: string[];
  direct: string[];
  inherited: string[];
  groups: Group[];
};

export default function UserEdit({ user, roles, direct, inherited, groups }: Props) {
  const { t } = useT();
  const directSet = new Set(direct);
  const inheritedSet = new Set(inherited);

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-1">
        {t(keys.permissions.user_edit.title, { email: user.email })}
      </h1>
      {user.full_name && <p className="text-sm text-muted-foreground mb-4">{user.full_name}</p>}

      {roles.length > 0 && (
        <p className="text-sm mb-4">
          <span className="font-medium">{t(keys.permissions.user_edit.roles_label)} </span>
          {roles.join(', ')}
        </p>
      )}

      <form method="post" action={`/permissions/users/${user.id}`} className="space-y-6">
        <input type="hidden" name="_method" value="put" />

        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t(keys.permissions.user_edit.empty)}</p>
        ) : (
          groups.map((group) => (
            <fieldset key={group.name} className="border rounded p-3">
              <legend className="px-2 font-medium">{group.name}</legend>
              <div className="space-y-1">
                {group.permissions.map((key) => {
                  const fromRole = inheritedSet.has(key);
                  return (
                    <label
                      key={key}
                      className="flex items-center gap-2 text-sm"
                      title={fromRole ? t(keys.permissions.user_edit.inherited_hint) : undefined}
                    >
                      <input
                        type="checkbox"
                        name="permissions"
                        value={key}
                        defaultChecked={directSet.has(key)}
                      />
                      <span className="font-mono">{key}</span>
                      {fromRole && (
                        <span className="text-xs text-muted-foreground">
                          ({t(keys.permissions.user_edit.inherited_badge)})
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))
        )}

        <div className="flex gap-2">
          <button type="submit" className="rounded bg-primary px-3 py-1.5 text-primary-foreground">
            {t(keys.permissions.user_edit.submit_button)}
          </button>
          <a href="/permissions" className="rounded border px-3 py-1.5">
            {t(keys.permissions.user_edit.cancel_link)}
          </a>
        </div>
      </form>
    </div>
  );
}
