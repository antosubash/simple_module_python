import { keys, useT } from '@simple-module-py/i18n';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { ROUTES } from '../routes';
import type { Setting, SettingScope } from '../types';

const SCOPE_TONE: Record<SettingScope, string> = {
  system: 'border-primary-200 bg-primary-50 text-primary-700',
  tenant: 'border-blue-200 bg-blue-50 text-blue-700',
  user: 'border-amber-200 bg-amber-50 text-amber-700',
};

const HEAD = 'text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground';

/** `#rgb` / `#rrggbb`, the only values worth previewing as a colour. */
const HEX_COLOR = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

interface Props {
  settings: Setting[];
  onDelete: (setting: Setting) => void;
}

/**
 * The override rows.
 *
 * Scope id rides under the key rather than in its own column: it is empty for
 * every system row, which is most of them, so a dedicated column spends a
 * fifth of the width on em dashes. Description is dropped entirely — it is
 * prose about why an override exists, which belongs on the row's edit form,
 * not in a table an admin scans for a key.
 */
export function StoreTable({ settings, onDelete }: Props) {
  const { t } = useT();

  return (
    <Table>
      <TableHeader className="bg-secondary/40">
        <TableRow>
          <TableHead className={`${HEAD} w-[110px]`}>{t(keys.settings.table.scope)}</TableHead>
          <TableHead className={HEAD}>{t(keys.settings.table.key)}</TableHead>
          <TableHead className={`${HEAD} hidden sm:table-cell w-[80px]`}>
            {t(keys.settings.table.value_type)}
          </TableHead>
          <TableHead className={`${HEAD} w-[28%]`}>{t(keys.settings.table.value)}</TableHead>
          <TableHead className={`${HEAD} w-[130px] text-right`}>
            {t(keys.settings.table.actions)}
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {settings.map((setting) => (
          <TableRow key={setting.id} className="hover:bg-secondary/40">
            <TableCell>
              <Badge variant="outline" className={SCOPE_TONE[setting.scope]}>
                {t(keys.settings.scopes[setting.scope])}
              </Badge>
            </TableCell>
            <TableCell>
              <div className="flex flex-col gap-0.5">
                <code className="font-mono text-[13px] text-foreground">{setting.key}</code>
                {setting.scope_id && (
                  <span className="text-[11.5px] text-muted-foreground">{setting.scope_id}</span>
                )}
              </div>
            </TableCell>
            <TableCell className="hidden sm:table-cell text-sm text-muted-foreground">
              {t(keys.settings.value_types_short[setting.value_type])}
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                {HEX_COLOR.test(setting.value) && (
                  <span
                    aria-hidden="true"
                    className="size-4 shrink-0 rounded border border-border"
                    style={{ background: setting.value }}
                  />
                )}
                <code className="font-mono text-[13px] truncate">{setting.value}</code>
              </div>
            </TableCell>
            <TableCell>
              <div className="flex items-center justify-end gap-1.5 text-[12.5px] font-medium">
                <a
                  href={ROUTES.edit(setting.id)}
                  className="text-primary-700 hover:text-primary-800"
                >
                  {t(keys.settings.browse.edit_link)}
                </a>
                <span aria-hidden="true" className="text-muted-foreground">
                  ·
                </span>
                <button
                  type="button"
                  onClick={() => onDelete(setting)}
                  className="text-destructive hover:underline"
                >
                  {t(keys.settings.browse.delete_link)}
                </button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
