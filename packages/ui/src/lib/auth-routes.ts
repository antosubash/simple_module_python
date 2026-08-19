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
