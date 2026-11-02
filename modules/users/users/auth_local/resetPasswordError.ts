/** Extract only fastapi-users' password-policy reason; other failures keep their fallback. */
export function resetPasswordReason(error: unknown): string | null {
  if (!error || typeof error !== 'object' || !('detail' in error)) return null;
  const detail = error.detail;
  if (!detail || typeof detail !== 'object' || !('code' in detail) || !('reason' in detail)) {
    return null;
  }
  return detail.code === 'RESET_PASSWORD_INVALID_PASSWORD' &&
    typeof detail.reason === 'string' &&
    detail.reason.trim() !== ''
    ? detail.reason
    : null;
}
