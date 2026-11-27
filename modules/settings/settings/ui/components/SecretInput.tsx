import { keys, useT } from '@simple-module-py/i18n';
import { PasswordInput } from '@simple-module-py/ui/components/PasswordInput';
import { Input } from '@simple-module-py/ui/components/ui/input';
import type { SettingsFieldRendererProps } from '@simple-module-py/ui/extensions';
import { useEffect, useRef, useState } from 'react';

export function SecretInput({
  field,
  value,
  onChange,
  className,
  ...controlProps
}: SettingsFieldRendererProps & { className: string }) {
  const { t } = useT();
  const [editing, setEditing] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const hasValue = typeof field.value === 'string' && field.value !== '';

  useEffect(() => {
    if (editing) input.current?.focus();
  }, [editing]);

  return (
    <div className="flex items-center gap-2">
      <div className="min-w-0 flex-1">
        {editing ? (
          <PasswordInput
            {...controlProps}
            ref={input}
            value={String(value ?? '')}
            autoComplete="new-password"
            onChange={(event) => onChange(field.name, event.target.value)}
            showLabel={t(keys.settings.modules_form.show_secret)}
            hideLabel={t(keys.settings.modules_form.hide_secret)}
            className={`font-mono ${className}`}
          />
        ) : (
          <Input
            {...controlProps}
            type="password"
            value={hasValue ? '••••••••••' : ''}
            placeholder={t(keys.settings.modules_form.secret_not_set)}
            readOnly
            className={`font-mono ${className}`}
          />
        )}
      </div>
      {editing ? (
        <button
          type="button"
          className="text-xs font-medium text-primary-700 hover:underline"
          onClick={() => {
            onChange(field.name, field.value);
            setEditing(false);
          }}
        >
          {t(keys.settings.form.cancel_button)}
        </button>
      ) : (
        <button
          type="button"
          className="shrink-0 text-xs font-medium text-primary-700 hover:underline"
          onClick={() => {
            setEditing(true);
            onChange(field.name, '');
          }}
        >
          {t(keys.settings.modules_form.set_new_value)}
        </button>
      )}
    </div>
  );
}
