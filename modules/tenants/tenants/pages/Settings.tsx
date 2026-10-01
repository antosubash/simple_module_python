import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { EmptyState } from '@simple-module-py/ui/components/EmptyState';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Settings2 } from 'lucide-react';
import { type TenantSetting, TenantSettingRow } from '../components/TenantSettingRow';

interface Props {
  tenant: { id: string; name: string; slug: string };
  settings: TenantSetting[];
}

/** The active organisation's overrides of the keys the platform lets it change. */
function Settings() {
  const { tenant, settings } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  return (
    <>
      <Head title={t(keys.tenants.settings.head_title)} />
      <PageShell
        title={t(keys.tenants.settings.title)}
        description={t(keys.tenants.settings.description, { name: tenant.name })}
      >
        {settings.length === 0 ? (
          <EmptyState
            icon={Settings2}
            title={t(keys.tenants.settings.empty_title)}
            description={t(keys.tenants.settings.empty_description)}
          />
        ) : (
          <Card className="divide-y overflow-hidden p-0">
            {settings.map((setting) => (
              <TenantSettingRow
                // Keyed by value too, so a reload after save resets the draft.
                key={`${setting.key}:${setting.value ?? ''}`}
                setting={setting}
                onChanged={() => router.reload()}
              />
            ))}
          </Card>
        )}
      </PageShell>
    </>
  );
}

Settings.layout = [AuthenticatedLayout];
export default Settings;
