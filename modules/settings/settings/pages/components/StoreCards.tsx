import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { ROUTES } from '../routes';
import type { Setting, SettingScope } from '../types';

const SCOPE_TONE: Record<SettingScope, string> = {
  system: 'border-primary-200 bg-primary-50 text-primary-700',
  tenant: 'border-blue-200 bg-blue-50 text-blue-700',
  user: 'border-amber-200 bg-amber-50 text-amber-700',
};

/** `#rgb` / `#rrggbb`, the only values worth previewing as a colour. */
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

interface Props {
  settings: Setting[];
  onDelete: (setting: Setting) => void;
}

/**
 * The override table folded into cards, for phones.
 *
 * A five-column table at 390px is a sideways scroll, and the columns that fall
 * off the right are Value and Actions — the two a reader came for. Stacked as
 * the deck's phone frame has it: scope pill and key, then type and value, then
 * the two actions at a full 44px each.
 */
export function StoreCards({ settings, onDelete }: Props) {
  const { t } = useT();

  return (
    <div className="flex flex-col gap-3 p-3 sm:hidden">
      {settings.map((setting) => (
        <div
          key={setting.id}
          className="flex flex-col gap-2 rounded-xl border border-border bg-card p-3.5"
        >
          <div className="flex items-start gap-2">
            <Badge variant="outline" className={`shrink-0 ${SCOPE_TONE[setting.scope]}`}>
              {t(keys.settings.scopes[setting.scope])}
            </Badge>
            <div className="min-w-0 flex-1">
              <code className="block break-all font-mono text-[13px] text-foreground">
                {setting.key}
              </code>
              {setting.scope_id && (
                <span className="block truncate text-[11.5px] text-muted-foreground">
                  {setting.scope_id}
                </span>
              )}
            </div>
          </div>

          <div className="flex min-w-0 items-center gap-2 text-[12.5px] text-muted-foreground">
            <span className="shrink-0">
              {t(keys.settings.value_types_short[setting.value_type])}
            </span>
            <span aria-hidden="true">·</span>
            {HEX_COLOR.test(setting.value) && (
              <span
                aria-hidden="true"
                className="size-4 shrink-0 rounded border border-border"
                style={{ background: setting.value }}
              />
            )}
            <code className="min-w-0 truncate font-mono text-[12.5px] text-foreground">
              {setting.value}
            </code>
          </div>

          <div className="flex items-center gap-3 border-t border-border pt-1 text-[13px] font-medium">
            <a
              href={ROUTES.edit(setting.id)}
              className="inline-flex min-h-11 items-center text-primary-700"
            >
              {t(keys.settings.browse.edit_link)}
            </a>
            <span aria-hidden="true" className="text-muted-foreground">
              ·
            </span>
            <button
              type="button"
              onClick={() => onDelete(setting)}
              className="inline-flex min-h-11 items-center text-destructive"
            >
              {t(keys.settings.browse.delete_link)}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
