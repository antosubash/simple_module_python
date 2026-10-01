import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { useState } from 'react';
import { toast } from 'sonner';
import { detail } from './apiDetail';

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
  const [busy, setBusy] = useState(false);

  async function send(init: RequestInit, success: string) {
    setBusy(true);
    try {
      const response = await fetch(uploadUrl, { credentials: 'same-origin', ...init });
      if (!response.ok) {
        toast.error((await detail(response)) ?? t(keys.tenants.settings.toast_failed));
        return;
      }
      toast.success(success);
      onChanged();
    } catch {
      toast.error(t(keys.tenants.settings.toast_failed));
    } finally {
      setBusy(false);
    }
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
