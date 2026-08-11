import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Switch } from '@simple-module-py/ui/components/ui/switch';
import { Check, Minus } from 'lucide-react';

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
 * thing this form can change. Previously that was also the row's only signal,
 * so a permission the user genuinely holds through a role rendered as "off".
 * The leading indicator now answers "does this user have it?" and the switch
 * answers "is it granted here?", which are different questions.
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
  const switchId = `perm-${permissionKey}`;

  return (
    <div className={`flex items-center gap-2.5 px-4 py-3 ${className}`}>
      <span
        aria-hidden="true"
        title={
          effective
            ? t(keys.permissions.user_edit.effective_yes)
            : t(keys.permissions.user_edit.effective_no)
        }
        className={`inline-flex size-5 shrink-0 items-center justify-center rounded-full ${
          effective ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground/60'
        }`}
      >
        {effective ? <Check className="size-3" /> : <Minus className="size-3" />}
      </span>

      <code
        className={`min-w-0 flex-1 truncate rounded bg-secondary px-2 py-0.5 font-mono text-[12px] ${
          effective ? 'text-foreground' : 'text-muted-foreground'
        }`}
      >
        {permissionKey}
      </code>

      {inherited && (
        <Badge
          variant="outline"
          className="shrink-0 border-blue-200 bg-blue-50 px-1.5 py-0 text-[10px] text-blue-700"
          // Naming the role is what makes this actionable: it tells the admin
          // which role to edit if they want to take the permission away.
          title={t(keys.permissions.user_edit.inherited_hint, { roles: viaRoles.join(', ') })}
        >
          {t(keys.permissions.user_edit.via_role, { role: viaRoles[0] })}
          {viaRoles.length > 1 ? ` +${viaRoles.length - 1}` : ''}
        </Badge>
      )}

      <Switch
        id={switchId}
        checked={direct}
        onCheckedChange={(c) => onToggle(permissionKey, c === true)}
        aria-label={t(keys.permissions.user_edit.direct_toggle_label, { key: permissionKey })}
        title={t(keys.permissions.user_edit.direct_toggle_label, { key: permissionKey })}
      />
    </div>
  );
}
