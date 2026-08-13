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
  /** A stored setting overrides this field. */
  db_override?: boolean;
  /** Where the live value came from. Mirrors hydrate_settings' precedence. */
  source?: 'db' | 'env' | 'default';
};

type Props = {
  field: FieldMeta;
  onChange: (name: string, value: unknown) => void;
  value: unknown;
  id?: string;
};

export function FieldInput({ field, onChange, value, id }: Props) {
  const [revealed, setRevealed] = useState(false);

  if (field.is_secret && !revealed) {
    return (
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="password"
          value="••••••••"
          readOnly
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
        <button
          type="button"
          className="text-sm text-primary hover:underline"
          onClick={() => {
            setRevealed(true);
            onChange(field.name, ''); // start blank
          }}
        >
          Set new value
        </button>
      </div>
    );
  }

  switch (field.type) {
    case 'bool':
      return (
        <input
          id={id}
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(field.name, e.target.checked)}
        />
      );
    case 'int':
    case 'float':
      return (
        <input
          id={id}
          type="number"
          step={field.type === 'int' ? '1' : 'any'}
          value={String(value ?? '')}
          onChange={(e) =>
            onChange(field.name, e.target.value === '' ? null : Number(e.target.value))
          }
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
      );
    case 'json':
      return (
        <textarea
          id={id}
          rows={3}
          value={typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
          onChange={(e) => onChange(field.name, e.target.value)}
          className="w-full rounded border px-2 py-1 font-mono text-xs"
        />
      );
    default:
      return (
        <input
          id={id}
          type="text"
          value={String(value ?? '')}
          onChange={(e) => onChange(field.name, e.target.value)}
          className="w-full rounded border px-2 py-1 font-mono text-sm"
        />
      );
  }
}
