import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { Flag } from 'lucide-react';

export interface PendingToggle {
  name: string;
  next: boolean;
}

interface Props {
  pending: PendingToggle | null;
  tenantId: string | null;
  onConfirm: (pending: PendingToggle) => void;
  onCancel: () => void;
}

/**
 * Confirms a flag flip before it is written.
 *
 * A flag toggle takes effect the instant the switch moves, with no undo and no
 * local record of who moved it — and the same switch means "for this tenant" or
 * "for everyone" depending on a scope selector further up the page. That scope
 * is the part worth restating: it is the difference between an experiment and
 * an outage, and it is the piece you cannot see from the switch itself.
 *
 * Rendered through the shared confirm so it looks like every other "are you
 * sure?" in the app — turning something off gets the same red tile as any
 * other change people should slow down for.
 */
export function ToggleConfirmDialog({ pending, tenantId, onConfirm, onCancel }: Props) {
  const { t } = useT();
  if (!pending) return null;

  // Spelled out per branch — `t` needs a literal key, not one built at runtime.
  const title = pending.next
    ? t(keys.feature_flags.confirm.enable_title, { name: pending.name })
    : t(keys.feature_flags.confirm.disable_title, { name: pending.name });
  const scope = tenantId
    ? t(keys.feature_flags.confirm.scope_tenant, { tenant_id: tenantId })
    : t(keys.feature_flags.confirm.scope_system);

  return (
    <ConfirmActionDialog
      open
      onOpenChange={(open) => !open && onCancel()}
      tone={pending.next ? 'primary' : 'destructive'}
      icon={Flag}
      title={title}
      description={scope}
      confirmLabel={
        pending.next
          ? t(keys.feature_flags.confirm.enable_action)
          : t(keys.feature_flags.confirm.disable_action)
      }
      cancelLabel={t(keys.feature_flags.confirm.cancel)}
      onConfirm={() => onConfirm(pending)}
    />
  );
}
