import { keys, useT } from '@simple-module-py/i18n';

export type ValueType = 'string' | 'bool' | 'int' | 'float' | 'json';

export const VALUE_TYPES: readonly ValueType[] = [
  'string',
  'bool',
  'int',
  'float',
  'json',
] as const;

type Props = {
  valueType: ValueType;
  value: string;
  onValueChange: (value: string) => void;
  required?: boolean;
};

/** Renders the appropriate HTML control for a given `value_type`.
 *
 * Controlled component — emits string values regardless of the declared type.
 * The server re-validates the string against `value_type`.
 */
export default function ValueInput({ valueType, value, onValueChange, required = false }: Props) {
  const { t } = useT();

  if (valueType === 'bool') {
    const current = value.toLowerCase();
    return (
      <select
        value={current || 'false'}
        onChange={(e) => onValueChange(e.target.value)}
        className="border rounded w-full p-2"
      >
        <option value="true">{t(keys.settings.form.bool_true)}</option>
        <option value="false">{t(keys.settings.form.bool_false)}</option>
      </select>
    );
  }

  if (valueType === 'int') {
    return (
      <input
        type="number"
        step="1"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        required={required}
        className="border rounded w-full p-2 font-mono"
      />
    );
  }

  if (valueType === 'float') {
    return (
      <input
        type="number"
        step="any"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        required={required}
        className="border rounded w-full p-2 font-mono"
      />
    );
  }

  if (valueType === 'json') {
    return (
      <textarea
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        required={required}
        rows={6}
        // i18n-exempt: a JSON example, shown verbatim.
        placeholder='{"key": "value"}'
        className="border rounded w-full p-2 font-mono text-sm"
      />
    );
  }

  // string (default)
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      required={required}
      placeholder={t(keys.settings.form.value_placeholder)}
      className="border rounded w-full p-2"
    />
  );
}
