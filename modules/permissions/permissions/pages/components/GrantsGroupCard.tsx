import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { GroupHeading } from './GroupHeading';
import { PermissionRow } from './PermissionRow';
import type { PermissionGroup } from './permission-groups';

interface Props {
  /** The whole module — the header counts what the user holds of all of it. */
  group: PermissionGroup;
  /** The rows the filter kept — a subset of `group.permissions`. */
  permissions: string[];
  /** Keys the user holds directly. */
  direct: Set<string>;
  /** Keys the user holds at all, directly or through a role. */
  effective: Set<string>;
  /** Permission key -> the roles granting it. */
  inheritedBy: Record<string, string[]>;
  onToggle: (key: string, checked: boolean) => void;
}

/** One module's permissions, as they land on a single user. */
export function GrantsGroupCard({
  group,
  permissions,
  direct,
  effective,
  inheritedBy,
  onToggle,
}: Props) {
  const { t } = useT();
  const granted = group.permissions.filter((key) => effective.has(key)).length;

  return (
    <Card className="gap-0 overflow-hidden border-border p-0">
      <div className="flex items-center gap-3 border-b border-border bg-secondary px-4 py-3">
        <GroupHeading group={group} />
        <span className="shrink-0 text-xs text-muted-foreground">
          {t(keys.permissions.user_edit.group_effective, {
            granted,
            total: group.permissions.length,
          })}
        </span>
      </div>
      <div className="flex flex-col">
        {permissions.map((key, index) => (
          <PermissionRow
            key={key}
            permissionKey={key}
            direct={direct.has(key)}
            viaRoles={inheritedBy[key] ?? []}
            onToggle={onToggle}
            className={index < permissions.length - 1 ? 'border-b border-border' : ''}
          />
        ))}
      </div>
    </Card>
  );
}
