import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import type { ValueType } from '../types';

export type { ValueType } from '../types';
export { VALUE_TYPES } from '../types';

type Props = {
  valueType: ValueType;
  value: string;
  onValueChange: (value: string) => void;
  required?: boolean;
};

/** Renders the appropriate control for a given `value_type`.
 *
 * Controlled component — emits string values regardless of the declared type.
 * The server re-validates the string against `value_type`.
 *
 * Every branch uses the shared form primitives so this input's radius, border
 * and focus ring match the Scope and Type fields sitting next to it; raw
 * `<input className="border rounded">` made the one field an admin actually
 * types into the only one that looked unfinished.
 */
export default function ValueInput({ valueType, value, onValueChange, required = false }: Props) {
  const { t } = useT();

  if (valueType === 'bool') {
    return (
      <Select value={value.toLowerCase() || 'false'} onValueChange={onValueChange}>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">{t(keys.settings.form.bool_true)}</SelectItem>
          <SelectItem value="false">{t(keys.settings.form.bool_false)}</SelectItem>
        </SelectContent>
      </Select>
    );
  }

  if (valueType === 'int' || valueType === 'float') {
    return (
      <Input
        type="number"
        step={valueType === 'int' ? '1' : 'any'}
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        required={required}
        className="font-mono"
      />
    );
  }

  if (valueType === 'json') {
    return (
      <Textarea
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        required={required}
        rows={6}
        // i18n-exempt: a JSON example, shown verbatim.
        placeholder='{"key": "value"}'
        className="font-mono text-sm"
      />
    );
  }

  return (
    <Input
      type="text"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      required={required}
      placeholder={t(keys.settings.form.value_placeholder)}
      className="font-mono"
    />
  );
}
