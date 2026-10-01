import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useState } from 'react';
import { toast } from 'sonner';
import { detail } from './apiDetail';

export interface TenantSetting {
  key: string;
  description: string;
  value_type: 'string' | 'bool' | 'int' | 'float' | 'json';
  inherited: string;
  value: string | null;
  effective: string;
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
      {setting.description && (
        <p className="text-sm text-muted-foreground">{setting.description}</p>
      )}
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
      <p className="text-xs text-muted-foreground">
        {t(keys.tenants.settings.inherited_value, {
          value: setting.inherited || t(keys.tenants.settings.none),
        })}
      </p>
    </div>
  );
}
