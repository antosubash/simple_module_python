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
