import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import { Switch } from '@simple-module-py/ui/components/ui/switch';
import {
  type SettingsFieldMeta,
  type SettingsFieldRendererProps,
  useExtensions,
} from '@simple-module-py/ui/extensions';
import { Suspense, useState } from 'react';
import { JsonInput } from './JsonInput';

export type { FieldType } from '@simple-module-py/ui/extensions';
export type FieldMeta = SettingsFieldMeta;
const UNSET = '__unset__';
type Props = SettingsFieldRendererProps;

/** A stored override is the one thing on this screen someone put there. */
const OVERRIDDEN = 'border-primary ring-[3px] ring-primary/10';

export function FieldInput({ field, onChange, value, id, 'aria-describedby': describedBy }: Props) {
  const registry = useExtensions();
  const { t } = useT();
  const [revealed, setRevealed] = useState(false);
  const highlight = field.db_override ? OVERRIDDEN : '';
  const kind = field.input_type ?? field.type;
  const nullable = !!field.nullable;

  if (field.is_secret && !revealed) {
    // Not "Reveal": the server never returns the stored value, so there is
    // nothing to uncover — only a new value to set. A reveal control here
    // would promise something the API deliberately cannot deliver.
    return (
      <div
        className={`flex h-9 items-center justify-between rounded-md border border-input px-3 py-1 ${highlight}`}
      >
        {/* A real input, not a styled span: the row's `<label htmlFor>` needs a
            labelable control to point at, and putting the id on the button
            instead would replace its own "Set new value" name with the field
            name for anyone listening to it. */}
        <input
          id={id}
          aria-describedby={describedBy}
          type="password"
          value="••••••••••"
          readOnly
          className="min-w-0 flex-1 bg-transparent font-mono text-sm text-muted-foreground outline-none"
        />
        <button
          type="button"
          className="text-xs font-medium text-primary-700 hover:underline"
          onClick={() => {
            setRevealed(true);
            onChange(field.name, ''); // start blank
          }}
        >
          {t(keys.settings.modules_form.set_new_value)}
        </button>
      </div>
    );
  }

  const Renderer = field.control ? registry.getFieldRenderer(field.control) : undefined;
  if (Renderer) {
    return (
      <Suspense fallback={null}>
        <Renderer
          field={field}
          value={value}
          onChange={onChange}
          id={id}
          aria-describedby={describedBy}
        />
      </Suspense>
    );
  }

  if (kind === 'bool' && nullable) {
    // `bool | None`: a switch cannot say "not set", which is the default.
    const current = value === null || value === undefined ? UNSET : String(value);
    return (
      <Select
        value={current}
        onValueChange={(next) => onChange(field.name, next === UNSET ? null : next === 'true')}
      >
        <SelectTrigger id={id} aria-describedby={describedBy} className={`w-[160px] ${highlight}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={UNSET}>{t(keys.settings.modules_form.not_set)}</SelectItem>
          <SelectItem value="true">{t(keys.settings.modules_form.option_on)}</SelectItem>
          <SelectItem value="false">{t(keys.settings.modules_form.option_off)}</SelectItem>
        </SelectContent>
      </Select>
    );
  }

  if (kind === 'bool') {
    return (
      <Switch
        id={id}
        aria-describedby={describedBy}
        checked={!!value}
        onCheckedChange={(next) => onChange(field.name, next)}
        className={highlight}
      />
    );
  }

  if (field.choices?.length) {
    // A pattern-constrained string is a closed list; a text box makes its only
    // feedback on a typo a 422 after Save.
    return (
      <Select value={String(value ?? '')} onValueChange={(next) => onChange(field.name, next)}>
        <SelectTrigger id={id} aria-describedby={describedBy} className={`w-full ${highlight}`}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {field.choices.map((choice) => (
            <SelectItem key={choice} value={choice}>
              {choice}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  if (kind === 'int' || kind === 'float') {
    return (
      <Input
        id={id}
        aria-describedby={describedBy}
        type="number"
        step={kind === 'int' ? '1' : 'any'}
        value={String(value ?? '')}
        onChange={(e) =>
          onChange(field.name, e.target.value === '' ? null : Number(e.target.value))
        }
        className={`w-[120px] font-mono ${highlight}`}
      />
    );
  }

  if (kind === 'json') {
    return (
      <JsonInput
        id={id}
        aria-describedby={describedBy}
        name={field.name}
        value={value}
        nullable={nullable}
        className={highlight}
        onChange={onChange}
      />
    );
  }

  return (
    <Input
      id={id}
      aria-describedby={describedBy}
      type="text"
      value={String(value ?? '')}
      onChange={(e) =>
        onChange(field.name, nullable && e.target.value === '' ? null : e.target.value)
      }
      className={`font-mono ${highlight}`}
    />
  );
}
