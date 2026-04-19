import { keys, useT } from '@simple-module/i18n';

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
  defaultValue?: string;
  name?: string;
  required?: boolean;
};

/** Renders the appropriate HTML control for a given `value_type`.
 *
 * All controls submit under the same `name` (default "value") so the form
 * payload looks identical regardless of the declared type — the server
 * re-validates the string against `value_type`.
 */
export default function ValueInput({
  valueType,
  defaultValue = '',
  name = 'value',
  required = false,
}: Props) {
  const { t } = useT();

  if (valueType === 'bool') {
    const current = defaultValue.toLowerCase();
    return (
      <select name={name} defaultValue={current || 'false'} className="border rounded w-full p-2">
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  }

  if (valueType === 'int') {
    return (
      <input
        type="number"
        step="1"
        name={name}
        defaultValue={defaultValue}
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
        name={name}
        defaultValue={defaultValue}
        required={required}
        className="border rounded w-full p-2 font-mono"
      />
    );
  }

  if (valueType === 'json') {
    return (
      <textarea
        name={name}
        defaultValue={defaultValue}
        required={required}
        rows={6}
        placeholder='{"key": "value"}'
        className="border rounded w-full p-2 font-mono text-sm"
      />
    );
  }

  // string (default)
  return (
    <input
      type="text"
      name={name}
      defaultValue={defaultValue}
      required={required}
      placeholder={t(keys.settings.form.value_placeholder)}
      className="border rounded w-full p-2"
    />
  );
}
