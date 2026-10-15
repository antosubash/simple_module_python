import { keys, useT } from '@simple-module-py/i18n';
import { ConfirmActionDialog } from '@simple-module-py/ui/components/ConfirmActionDialog';
import { KeyRound } from 'lucide-react';
import type { ApiToken } from '../types';

interface Props {
  token: ApiToken | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function RevokeTokenDialog({ token, busy, onCancel, onConfirm }: Props) {
  const { t } = useT();
  return (
    <ConfirmActionDialog
      open={token !== null}
      onOpenChange={(open) => !open && onCancel()}
      tone="destructive"
      icon={KeyRound}
      title={t(keys.api_tokens.revoke.title, { name: token?.name ?? '' })}
      description={t(keys.api_tokens.revoke.description)}
      confirmLabel={t(keys.api_tokens.revoke.confirm)}
      cancelLabel={t(keys.api_tokens.revoke.cancel)}
      busy={busy}
      onConfirm={onConfirm}
    />
  );
}
