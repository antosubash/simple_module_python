import { stripValueErrorPrefix } from './validation-errors';

/**
 * A validation error that belongs to no single field — a model-level
 * validator (e.g. "tenant/user scope requires a scope_id") is flashed under
 * `errors.general`, which the per-field slots never render.
 */
export function FormLevelError({
  errors,
  className = '',
}: {
  errors: Partial<Record<string, string>>;
  className?: string;
}) {
  const message = errors.general && stripValueErrorPrefix(errors.general);
  if (!message) return null;
  return (
    <p role="alert" className={`text-sm text-destructive ${className}`.trim()}>
      {message}
    </p>
  );
}
