import { keys, useT } from '@simple-module/i18n';

type Setting = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
};

type Props = { settings: Setting[] };

export default function Browse({ settings }: Props) {
  const { t } = useT();
  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold">{t(keys.settings.browse.title)}</h1>
        <a
          href="/settings/create"
          className="rounded bg-primary px-3 py-1.5 text-primary-foreground"
        >
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
        <ul className="divide-y">
          {settings.map((setting) => (
            <li key={setting.id} className="py-2 flex justify-between">
              <span>{setting.name}</span>
              <a href={`/settings/${setting.id}/edit`}>{t(keys.settings.browse.edit_link)}</a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
