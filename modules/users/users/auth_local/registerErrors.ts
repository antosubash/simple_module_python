/**
 * Maps a failed `POST /api/users/auth/register` onto the field that caused it.
 *
 * The API answers three ways: fastapi-users' `400 {"detail": "REGISTER_USER_ALREADY_EXISTS"}`,
 * `400 {"detail": {"code": "REGISTER_INVALID_PASSWORD", "reason": "<english>"}}`
 * (reasons come from `UserManager.validate_password`), and pydantic's
 * `422 {"detail": [{"loc": ["body", "email"], "msg": "..."}]}`. Server strings
 * are never shown: each is reduced to a code the page translates.
 */
export type RegisterErrorCode =
  | 'exists'
  | 'email_invalid'
  | 'password_length'
  | 'password_contains_email'
  | 'password_numeric'
  | 'password_invalid'
  | 'failed';

export interface RegisterError {
  field: 'email' | 'password' | 'form';
  code: RegisterErrorCode;
}

const FAILED: RegisterError = { field: 'form', code: 'failed' };

/** Mirrors `UserManager.validate_password`: the client threshold is the server's. */
export const MIN_PASSWORD_LENGTH = 8;

export function meetsPasswordPolicy(password: string, email: string): boolean {
  if (password.trim().length < MIN_PASSWORD_LENGTH) return false;
  if (/^\d+$/.test(password)) return false;
  return !(email !== '' && email.toLowerCase().includes(password.toLowerCase()));
}

function passwordReason(reason: unknown): RegisterErrorCode {
  const text = typeof reason === 'string' ? reason.toLowerCase() : '';
  if (text.includes('at least')) return 'password_length';
  if (text.includes('email')) return 'password_contains_email';
  if (text.includes('numbers')) return 'password_numeric';
  return 'password_invalid';
}

export function mapRegisterError(data: unknown): RegisterError {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (detail === 'REGISTER_USER_ALREADY_EXISTS') return { field: 'email', code: 'exists' };
  if (Array.isArray(detail)) {
    for (const item of detail as { loc?: unknown[] }[]) {
      const field = item?.loc?.[item.loc.length - 1];
      if (field === 'email') return { field: 'email', code: 'email_invalid' };
      if (field === 'password') return { field: 'password', code: 'password_invalid' };
    }
    return FAILED;
  }
  if (detail && typeof detail === 'object') {
    const d = detail as { code?: unknown; reason?: unknown };
    if (d.code === 'REGISTER_INVALID_PASSWORD') {
      return { field: 'password', code: passwordReason(d.reason) };
    }
  }
  return FAILED;
}
