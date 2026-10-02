import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useState } from 'react';
import { toast } from 'sonner';
import { detail } from './apiDetail';
import { TenantImageControl } from './TenantImageControl';

export interface TenantSetting {
  key: string;
  description: string;
  value_type: 'string' | 'bool' | 'int' | 'float' | 'json';
  inherited: string;
  value: string | null;
  effective: string;
  /** Set for a file-id key (a logo): upload/clear there instead of typing an id. */
  upload_url: string;
  /** i18n key for `description`, owned by the module that declared the key;
   * `description` (English) is the fallback when it is unset or missing. */
  description_key?: string;
}

interface Props {
  setting: TenantSetting;
  onChanged: () => void;
}

const API = '/api/settings/tenant/current';

/** One overridable key: its inherited value, the organisation's override, save/reset. */
export function TenantSettingRow({ setting, onChanged }: Props) {
  const { t } = useT();
  const [draft, setDraft] = useState(setting.value ?? '');
  const [busy, setBusy] = useState(false);
  const overridden = setting.value !== null;
  // A key declared by another module: not in this file's typed key set, so it
  // is looked up dynamically, with the server's English text as the default.
  const description = setting.description_key
    ? t(setting.description_key as never, { defaultValue: setting.description })
    : setting.description;
  const inputId = `tenant-setting-${setting.key}`;

  async function send(method: 'PUT' | 'DELETE') {
    setBusy(true);
    try {
      const response = await fetch(`${API}/${encodeURIComponent(setting.key)}`, {
        method,
        credentials: 'same-origin',
        headers: method === 'PUT' ? { 'Content-Type': 'application/json' } : undefined,
        body: method === 'PUT' ? JSON.stringify({ value: draft }) : undefined,
      });
      if (!response.ok) {
        toast.error((await detail(response)) ?? t(keys.tenants.settings.toast_failed));
        return;
      }
      toast.success(
        t(method === 'PUT' ? keys.tenants.settings.toast_saved : keys.tenants.settings.toast_reset),
      );
      onChanged();
    } catch {
      toast.error(t(keys.tenants.settings.toast_failed));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor={inputId} className="font-mono text-sm">
          {setting.key}
        </Label>
        <Badge variant={overridden ? 'default' : 'secondary'}>
          {t(overridden ? keys.tenants.settings.overridden : keys.tenants.settings.inherited)}
        </Badge>
      </div>
      {description && <p className="text-sm text-muted-foreground">{description}</p>}
      {setting.upload_url ? (
        <TenantImageControl
          inputId={inputId}
          uploadUrl={setting.upload_url}
          overridden={overridden}
          onChanged={onChanged}
        />
      ) : (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input
            id={inputId}
            value={draft}
            placeholder={setting.inherited}
            onChange={(event) => setDraft(event.target.value)}
            disabled={busy}
          />
          <div className="flex shrink-0 gap-2">
            <Button size="sm" disabled={busy} onClick={() => send('PUT')}>
              {t(keys.tenants.settings.save)}
            </Button>
            {overridden && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => send('DELETE')}>
                {t(keys.tenants.settings.reset)}
              </Button>
            )}
          </div>
        </div>
      )}
      {!setting.upload_url && (
        <p className="text-xs text-muted-foreground">
          {t(keys.tenants.settings.inherited_value, {
            value: setting.inherited || t(keys.tenants.settings.none),
          })}
        </p>
      )}
    </div>
  );
}
