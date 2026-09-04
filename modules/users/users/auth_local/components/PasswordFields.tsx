import { keys, useT } from '@simple-module-py/i18n';
import { PasswordInput } from '@simple-module-py/ui/components/PasswordInput';
import { PasswordStrength } from '@simple-module-py/ui/components/PasswordStrength';
import { AuthField } from './AuthField';

interface PasswordFieldsProps {
  password: string;
  onPasswordChange: (next: string) => void;
  confirm: string;
  onConfirmChange: (next: string) => void;
  /** Label for the first field — "Password" on sign-up, "New password" on reset. */
  passwordLabel: string;
  /** "Confirm password" on the wider cards, "Confirm" on the narrow reset card. */
  confirmLabel: string;
  /** Set once the form has been submitted with two different values. */
  mismatch?: boolean;
  /** The rule shown under the meter. Omitted where the deck shows none. */
  hint?: string;
}

/**
 * Choose-a-password, twice, with live feedback.
 *
 * Register, reset and accept-invite all ask the same question and all used to
 * answer a mismatch with one line under the whole form, far from the field
 * that caused it. Here the confirm field carries its own error and
 * `aria-invalid`, so screen readers and eyes learn the same thing.
 */
export function PasswordFields({
  password,
  onPasswordChange,
  confirm,
  onConfirmChange,
  passwordLabel,
  confirmLabel,
  mismatch = false,
  hint,
}: PasswordFieldsProps) {
  const { t } = useT();
  const reveal = {
    showLabel: t(keys.users.common.show_password),
    hideLabel: t(keys.users.common.hide_password),
  };

  return (
    <>
      <AuthField htmlFor="password" label={passwordLabel}>
        <PasswordInput
          id="password"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          required
          autoComplete="new-password"
          {...reveal}
        />
        <PasswordStrength
          className="pt-1"
          password={password}
          hint={hint}
          labels={{
            weak: t(keys.users.common.strength_weak),
            ok: t(keys.users.common.strength_ok),
            strong: t(keys.users.common.strength_strong),
          }}
        />
      </AuthField>
      <AuthField
        htmlFor="confirm"
        label={confirmLabel}
        error={mismatch ? t(keys.users.common.passwords_no_match) : null}
      >
        <PasswordInput
          id="confirm"
          value={confirm}
          onChange={(e) => onConfirmChange(e.target.value)}
          required
          autoComplete="new-password"
          aria-invalid={mismatch || undefined}
          {...reveal}
        />
      </AuthField>
    </>
  );
}
