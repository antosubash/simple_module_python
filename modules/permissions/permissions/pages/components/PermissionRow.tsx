import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Switch } from '@simple-module-py/ui/components/ui/switch';

interface Props {
  permissionKey: string;
  /** Granted directly to this user — the only thing the switch controls. */
  direct: boolean;
  /** Roles granting this key, empty when none do. */
  viaRoles: string[];
  onToggle: (key: string, checked: boolean) => void;
  className?: string;
}

/**
 * One permission, showing *effective* access separately from the direct grant.
 *
 * The switch reflects only the direct grant, which is correct — it is the only
 * thing this form can change. The badges carry the rest: "direct" for what the
 * switch holds, "granted by …" for what a role holds, and both together when
 * both are true, because turning the switch off would not revoke that key.
 */
export function PermissionRow({
  permissionKey,
  direct,
  viaRoles,
  onToggle,
  className = '',
}: Props) {
  const { t } = useT();
  const inherited = viaRoles.length > 0;
  const effective = direct || inherited;

  const switchId = `grant-${permissionKey}`;

  return (
    // A `label`, as the role editor's rows already are: the whole row is the
    // 44px target, not the 20px switch inside it.
    <label
      htmlFor={switchId}
      className={`flex min-h-11 cursor-pointer items-center gap-3 px-4 py-3 ${className}`}
    >
      <Switch
        id={switchId}
        checked={direct}
        onCheckedChange={(checked) => onToggle(permissionKey, checked === true)}
        aria-label={t(keys.permissions.user_edit.direct_toggle_label, { key: permissionKey })}
        title={t(keys.permissions.user_edit.direct_toggle_label, { key: permissionKey })}
      />

      {/* Wrapping beats truncating on a phone: a permission key is read from
          the right — `settings.create`, `settings.delete` — so cutting the end
          off removes the half that tells them apart. */}
      <code
        className={`min-w-0 flex-1 break-all font-mono text-[12px] sm:truncate ${
          effective ? 'text-foreground' : 'text-muted-foreground'
        }`}
      >
        {permissionKey}
      </code>

      {direct && (
        <Badge className="shrink-0 border-0 bg-primary-600/10 px-2 py-0 text-[11px] font-medium text-primary-700">
          {t(keys.permissions.user_edit.direct_badge)}
        </Badge>
      )}

      {inherited && (
        <Badge
          variant="outline"
          className="shrink-0 border-blue-200 bg-blue-50 px-2 py-0 text-[11px] font-medium text-blue-700"
          // Naming the role is what makes this actionable: it tells the admin
          // which role to edit if they want to take the permission away.
          title={t(keys.permissions.user_edit.inherited_hint, { roles: viaRoles.join(', ') })}
        >
          {t(keys.permissions.user_edit.via_role, { roles: viaRoles.join(', ') })}
        </Badge>
      )}
    </label>
  );
}
