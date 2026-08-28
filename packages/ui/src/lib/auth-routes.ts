import { keys } from '@simple-module-py/i18n';

/**
 * Where the public shell sends visitors to authenticate.
 *
 * These are the users module's *view* routes, mounted under its `/users` view
 * prefix. `/auth/*` is the JSON API prefix (`/api/users/auth/login`) and has no
 * GET page behind it, so linking a visitor there renders a 404 — which is
 * exactly the drift these constants exist to stop repeating.
 */
export const LOGIN_PATH = '/users/login';
export const REGISTER_PATH = '/users/register';

/**
 * The public "sign in or sign up" call to action, gated on whether signup is
 * open. Bundles the href and its matching label so a caller can't update one
 * half of the swap (e.g. the link) without the other (e.g. the button text).
 *
 * Returns a catalog *key* rather than display text. The label used to be a
 * hardcoded English literal here, which shipped untranslated to every locale —
 * and `make ci-check-untranslated` could not see it, because a string reaching
 * the screen through a returned object is exactly the taint-analysis blind
 * spot that check documents. Handing back a key makes the omission a type
 * error instead of a silent one.
 */
export function authCta(signupOpen: boolean): {
  href: string;
  labelKey: typeof keys.ui.public_nav.sign_up | typeof keys.ui.public_nav.log_in;
} {
  return signupOpen
    ? { href: REGISTER_PATH, labelKey: keys.ui.public_nav.sign_up }
    : { href: LOGIN_PATH, labelKey: keys.ui.public_nav.log_in };
}

/**
 * The Users admin screen's url, as registered by the users module's menu
 * item (`_URL_USERS_ADMIN` in `users/module.py`, mirrored by `_ADMIN_URL` in
 * `permissions/endpoints/views.py`).
 *
 * Permissions pages (`RoleEdit`, `UserEdit`) live outside `/users` but are
 * reached from — and conceptually belong to — this screen, so they declare
 * it as their breadcrumb/nav `section`. One shared constant instead of a
 * literal per call site keeps those declarations from drifting apart from
 * each other if the route ever moves.
 */
export const USERS_ADMIN_PATH = '/admin/users/';
