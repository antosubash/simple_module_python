/** The row shape `admin/queries.py::list_users` sends, shared by every view of it. */
export interface UserListItem {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  is_external: boolean;
  disabled_at?: string | null;
  last_login_at: string | null;
  created_at: string | null;
  invited_at: string | null;
  invite_expires_at: string | null;
  /** Computed server-side so the pill, the filter and the count cannot drift. */
  state: UserState;
  roles: string[];
}

export type UserState = 'active' | 'unverified' | 'invited' | 'disabled';

/** Tailwind classes for the soft status pill each state wears. */
export const STATE_PILL: Record<UserState, string> = {
  active: 'bg-primary-600/10 text-primary-700 dark:text-primary-400',
  unverified: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  invited: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  disabled: 'bg-secondary text-muted-foreground',
};

/**
 * The same rule `admin/user_state.py::user_state` applies, for a row the
 * client has already changed.
 *
 * Disabling an account from the edit page updates local state without a
 * reload, so the header pill has to be recomputed rather than read off the
 * prop it was rendered from — otherwise re-enabling a disabled user leaves the
 * pill saying "disabled" about an account that is now active.
 */
export function deriveState(
  isActive: boolean,
  isVerified: boolean,
  invitedAt: string | null,
): UserState {
  if (!isActive) return 'disabled';
  if (isVerified) return 'active';
  return invitedAt ? 'invited' : 'unverified';
}
