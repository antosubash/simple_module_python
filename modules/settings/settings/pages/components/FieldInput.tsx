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
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { useState } from 'react';

export type FieldType = 'bool' | 'int' | 'float' | 'string' | 'json';

export type FieldMeta = {
  name: string;
  type: FieldType;
  value: unknown;
  default: unknown;
  description: string;
  is_secret: boolean;
  requires_restart: boolean;
  group: string | null;
  env_var: string;
  /** The field's SM_* env var is present in the process environment. */
  env_set?: boolean;
  /** The declaring settings class reads env at all (declares an `env_prefix`). */
  env_readable?: boolean;
  /** A stored setting overrides this field. */
  db_override?: boolean;
  /** Where the live value came from. Mirrors hydrate_settings' precedence. */
  source?: 'db' | 'env' | 'default';
  /** Closed set of accepted values, or null when the field is free text. */
  choices?: string[] | null;
};

type Props = {
  field: FieldMeta;
  onChange: (name: string, value: unknown) => void;
  value: unknown;
  id?: string;
};

/** A stored override is the one thing on this screen someone put there. */
const OVERRIDDEN = 'border-primary ring-[3px] ring-primary/10';

export function FieldInput({ field, onChange, value, id }: Props) {
  const { t } = useT();
  const [revealed, setRevealed] = useState(false);
  const highlight = field.db_override ? OVERRIDDEN : '';

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

  if (field.type === 'bool') {
    return (
      <Switch
        id={id}
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
        <SelectTrigger id={id} className={`w-full ${highlight}`}>
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

  if (field.type === 'int' || field.type === 'float') {
    return (
      <Input
        id={id}
        type="number"
        step={field.type === 'int' ? '1' : 'any'}
        value={String(value ?? '')}
        onChange={(e) =>
          onChange(field.name, e.target.value === '' ? null : Number(e.target.value))
        }
        className={`w-[120px] font-mono ${highlight}`}
      />
    );
  }

  if (field.type === 'json') {
    return (
      <Textarea
        id={id}
        rows={3}
        value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
        onChange={(e) => onChange(field.name, e.target.value)}
        className={`font-mono text-xs ${highlight}`}
      />
    );
  }

  return (
    <Input
      id={id}
      type="text"
      value={String(value ?? '')}
      onChange={(e) => onChange(field.name, e.target.value)}
      className={`font-mono ${highlight}`}
    />
  );
}
