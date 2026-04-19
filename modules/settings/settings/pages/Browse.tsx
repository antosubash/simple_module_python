import { keys, useT } from '@simple-module/i18n';
import { ROUTES } from './routes';

type Scope = 'system' | 'tenant' | 'user';

type Setting = {
  id: number;
  scope: Scope;
  scope_id: string;
  key: string;
  value: string;
  description: string | null;
};

type Props = { settings: Setting[] };

export default function Browse({ settings }: Props) {
  const { t } = useT();
  const scopeLabel = (scope: Scope) => t(keys.settings.scopes[scope]);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">{t(keys.settings.browse.title)}</h1>
        <a href={ROUTES.create} className="rounded bg-primary px-3 py-1.5 text-primary-foreground">
          {t(keys.settings.browse.new_button)}
        </a>
      </div>
      {settings.length === 0 ? (
        <div className="py-12 text-center">
          <h2 className="text-lg font-medium">{t(keys.settings.browse.empty_title)}</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {t(keys.settings.browse.empty_description)}
          </p>
        </div>
      ) : (
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b">
              <th className="py-2 pr-4">{t(keys.settings.table.scope)}</th>
              <th className="py-2 pr-4">{t(keys.settings.table.scope_id)}</th>
              <th className="py-2 pr-4">{t(keys.settings.table.key)}</th>
              <th className="py-2 pr-4">{t(keys.settings.table.value)}</th>
              <th className="py-2 pr-4">{t(keys.settings.table.description)}</th>
              <th className="py-2">{t(keys.settings.table.actions)}</th>
            </tr>
          </thead>
          <tbody>
            {settings.map((setting) => (
              <tr key={setting.id} className="border-b">
                <td className="py-2 pr-4">{scopeLabel(setting.scope)}</td>
                <td className="py-2 pr-4 font-mono text-sm text-muted-foreground">
                  {setting.scope_id || '—'}
                </td>
                <td className="py-2 pr-4 font-mono text-sm">{setting.key}</td>
                <td className="py-2 pr-4">{setting.value}</td>
                <td className="py-2 pr-4 text-muted-foreground">{setting.description ?? ''}</td>
                <td className="py-2">
                  <a href={ROUTES.edit(setting.id)}>{t(keys.settings.browse.edit_link)}</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
