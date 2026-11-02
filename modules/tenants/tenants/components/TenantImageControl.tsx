import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { useApiErrorToast } from '@simple-module-py/ui/hooks/use-api-error-toast';
import { apiFetch } from '@simple-module-py/ui/lib/api';
import { useState } from 'react';
import { toast } from 'sonner';

interface Props {
  inputId: string;
  uploadUrl: string;
  overridden: boolean;
  onChanged: () => void;
}

/**
 * A file-id setting (a logo, a favicon): the value is set by uploading to the
 * key's `upload_url` and cleared by DELETE there — the server owns the id, so
 * there is no text box for it.
 */
export function TenantImageControl({ inputId, uploadUrl, overridden, onChanged }: Props) {
  const { t } = useT();
  const showError = useApiErrorToast(keys.tenants.settings.toast_failed);
  const [busy, setBusy] = useState(false);

  async function send(init: RequestInit, success: string) {
    setBusy(true);
    // A server-supplied upload URL (another module's route) and a multipart body.
    const result = await apiFetch(uploadUrl, init);
    setBusy(false);
    if (!result.ok) {
      showError(result);
      return;
    }
    toast.success(success);
    onChanged();
  }

  function upload(file: File | undefined) {
    if (!file) return;
    const body = new FormData();
    body.append('file', file);
    void send({ method: 'POST', body }, t(keys.tenants.settings.toast_uploaded));
  }

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Input
        id={inputId}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp,image/x-icon"
        disabled={busy}
        onChange={(event) => upload(event.target.files?.[0])}
      />
      {overridden && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => send({ method: 'DELETE' }, t(keys.tenants.settings.toast_reset))}
        >
          {t(keys.tenants.settings.reset)}
        </Button>
      )}
    </div>
  );
}
