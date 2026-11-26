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
import { TOUCH_TARGET_CLASS } from '@simple-module-py/ui/lib/utils';
import { Suspense } from 'react';
import { JsonInput } from './JsonInput';
import { SecretInput } from './SecretInput';

export type { FieldType } from '@simple-module-py/ui/extensions';
export type FieldMeta = SettingsFieldMeta;
const UNSET = '__unset__';
type Props = SettingsFieldRendererProps;

/** A stored override is the one thing on this screen someone put there. */
const OVERRIDDEN = 'border-primary ring-[3px] ring-primary/10';

export function FieldInput({
  field,
  onChange,
  value,
  id,
  'aria-describedby': describedBy,
  'aria-invalid': invalid,
}: Props) {
  const registry = useExtensions();
  const { t } = useT();
  const highlight = field.db_override ? OVERRIDDEN : '';
  const kind = field.input_type ?? field.type;
  const nullable = !!field.nullable;

  if (field.is_secret) {
    return (
      <SecretInput
        field={field}
        value={value}
        onChange={onChange}
        id={id}
        aria-describedby={describedBy}
        aria-invalid={invalid}
        className={highlight}
      />
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
          aria-invalid={invalid}
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
        <SelectTrigger
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={`w-[160px] ${highlight}`}
        >
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
        aria-invalid={invalid}
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
        <SelectTrigger
          id={id}
          aria-describedby={describedBy}
          aria-invalid={invalid}
          className={`w-full ${highlight}`}
        >
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
        aria-invalid={invalid}
        type="number"
        step={kind === 'int' ? '1' : 'any'}
        value={String(value ?? '')}
        onChange={(e) =>
          onChange(field.name, e.target.value === '' ? null : Number(e.target.value))
        }
        className={`w-[120px] font-mono ${TOUCH_TARGET_CLASS} ${highlight}`}
      />
    );
  }

  if (kind === 'json') {
    return (
      <JsonInput
        id={id}
        aria-describedby={describedBy}
        aria-invalid={invalid}
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
      aria-invalid={invalid}
      type="text"
      value={String(value ?? '')}
      onChange={(e) =>
        onChange(field.name, nullable && e.target.value === '' ? null : e.target.value)
      }
      className={`font-mono ${highlight}`}
    />
  );
}
