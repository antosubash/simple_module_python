/** The `UserRead` shape `auth_local/views.py::profile_page` hands the page. */
export interface ProfileUser {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_verified: boolean;
  /** SSO account: no local password, so the Password card has nothing to change. */
  is_external: boolean;
  last_login_at: string | null;
}
