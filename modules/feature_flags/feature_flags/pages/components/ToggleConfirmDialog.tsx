import { keys, useT } from '@simple-module-py/i18n';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@simple-module-py/ui/components/ui/alert-dialog';

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
    <AlertDialog open onOpenChange={(open) => !open && onCancel()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{scope}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>
            {t(keys.feature_flags.confirm.cancel)}
          </AlertDialogCancel>
          <AlertDialogAction
            variant={pending.next ? 'default' : 'destructive'}
            onClick={() => onConfirm(pending)}
          >
            {pending.next
              ? t(keys.feature_flags.confirm.enable_action)
              : t(keys.feature_flags.confirm.disable_action)}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
