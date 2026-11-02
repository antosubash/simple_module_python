import { type ApiResult, apiResult } from '@simple-module-py/ui/lib/api';
import { api } from './api';

/**
 * Password sign-in. The route takes a form-encoded body (the OAuth2 password
 * form), so the typed client is given an explicit serializer; a 204 is success.
 */
export function signIn(
  username: string,
  password: string,
  remember = false,
): Promise<ApiResult<unknown>> {
  return apiResult(
    api.POST('/api/users/auth/login', {
      body: { username, password, remember },
      bodySerializer: (b) =>
        new URLSearchParams({
          username: b.username,
          password: b.password,
          remember: String(b.remember),
        }),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  );
}
