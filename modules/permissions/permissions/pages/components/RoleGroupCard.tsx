import { keys, useT } from '@simple-module-py/i18n';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { Checkbox } from '@simple-module-py/ui/components/ui/checkbox';
import { Switch } from '@simple-module-py/ui/components/ui/switch';
import { Minus } from 'lucide-react';
import { GroupHeading } from './GroupHeading';
import { lastRowStart, type PermissionGroup } from './permission-groups';

interface Props {
  /** The whole module: the header counts and its checkbox speak for all of it. */
  group: PermissionGroup;
  /** The rows the filters kept — a subset of `group.permissions`. */
  permissions: string[];
  assigned: Set<string>;
  onToggle: (key: string, checked: boolean) => void;
  onToggleGroup: (group: PermissionGroup, checked: boolean) => void;
}

/** One module of permissions, granted to a role a key or a module at a time. */
export function RoleGroupCard({ group, permissions, assigned, onToggle, onToggleGroup }: Props) {
  const { t } = useT();
  const granted = group.permissions.filter((key) => assigned.has(key)).length;
  const all = granted > 0 && granted === group.permissions.length;
  // Partial is its own answer, not a rounded-down "off": the header has to say
  // "some of this module" or clicking it looks like it grants from nothing.
  const state: boolean | 'indeterminate' = all ? true : granted > 0 ? 'indeterminate' : false;
  const lastRow = lastRowStart(permissions.length);

  return (
    <Card className="gap-0 overflow-hidden border-border p-0">
      <div className="flex items-center gap-3 border-b border-border bg-secondary px-4 py-3">
        <span className="relative inline-flex shrink-0">
          <Checkbox
            checked={state}
            onCheckedChange={() => onToggleGroup(group, !all)}
            aria-label={t(keys.permissions.edit.toggle_group_label, { group: group.name })}
            className={`size-[17px] rounded-[5px] ${
              state === 'indeterminate'
                ? // The vendored checkbox always draws a tick; a partial module
                  // is a dash, so the tick is hidden and the dash laid over it.
                  'border-primary bg-primary text-primary-foreground [&_svg]:hidden'
                : ''
            }`}
          />
          {state === 'indeterminate' && (
            <Minus
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 m-auto size-3 text-primary-foreground"
            />
          )}
        </span>
        <GroupHeading group={group} />
        <span className="shrink-0 text-xs text-muted-foreground">
          {granted} / {group.permissions.length}
        </span>
      </div>
      <div className="grid sm:grid-cols-2">
        {permissions.map((key, index) => {
          const on = assigned.has(key);
          return (
            <label
              key={key}
              htmlFor={`perm-${key}`}
              className={`flex cursor-pointer items-center gap-2.5 px-4 py-3 ${
                index % 2 === 0 ? 'sm:border-r sm:border-border' : ''
              } ${index < lastRow ? 'border-b border-border' : ''}`}
            >
              <Switch
                id={`perm-${key}`}
                checked={on}
                onCheckedChange={(checked) => onToggle(key, checked === true)}
              />
              <code
                className={`min-w-0 truncate font-mono text-[12px] ${
                  on ? 'text-foreground' : 'text-muted-foreground'
                }`}
              >
                {key}
              </code>
            </label>
          );
        })}
        {permissions.length % 2 === 1 && (
          // Keeps the last row's divider running the full width of the card.
          <div aria-hidden="true" className="hidden px-4 py-3 sm:block" />
        )}
      </div>
    </Card>
  );
}
