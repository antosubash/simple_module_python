import { keys, useT } from '@simple-module-py/i18n';
import { Textarea } from '@simple-module-py/ui/components/ui/textarea';
import { useEffect, useRef, useState } from 'react';

type Props = {
  id?: string;
  name: string;
  value: unknown;
  nullable: boolean;
  className: string;
  onChange: (name: string, value: unknown) => void;
};

function toText(value: unknown): string {
  return value === null || value === undefined ? '' : JSON.stringify(value, null, 2);
}

/**
 * A list/dict field, edited as JSON text and sent as the parsed value.
 *
 * Sending the textarea's text stored a JSON *string* for a dict field, which
 * hydration could not read back as a dict (GH #487). Unparseable text is still
 * sent as-is, so the server's 422 names the field; the inline hint just says
 * why before Save.
 */
export function JsonInput({ id, name, value, nullable, className, onChange }: Props) {
  const { t } = useT();
  const [text, setText] = useState(() => toText(value));
  const [invalid, setInvalid] = useState(false);
  // The last value this input emitted. Anything else arriving as `value` came
  // from outside (Revert, a props reload) and replaces the text.
  const emitted = useRef<unknown>(value);

  useEffect(() => {
    if (value === emitted.current) return;
    emitted.current = value;
    setText(toText(value));
    setInvalid(false);
  }, [value]);

  function emit(next: unknown) {
    emitted.current = next;
    onChange(name, next);
  }

  function update(next: string) {
    setText(next);
    if (next.trim() === '' && nullable) {
      setInvalid(false);
      emit(null);
      return;
    }
    try {
      emit(JSON.parse(next));
      setInvalid(false);
    } catch {
      setInvalid(true);
      emit(next);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <Textarea
        id={id}
        rows={3}
        value={text}
        aria-invalid={invalid}
        onChange={(e) => update(e.target.value)}
        className={`font-mono text-xs ${className}`}
      />
      {invalid && (
        <p className="text-xs text-destructive">{t(keys.settings.modules_form.invalid_json)}</p>
      )}
    </div>
  );
}
