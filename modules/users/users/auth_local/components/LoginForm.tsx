import { keys, useT } from '@simple-module-py/i18n';
import { PasswordInput } from '@simple-module-py/ui/components/PasswordInput';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Checkbox } from '@simple-module-py/ui/components/ui/checkbox';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { REGISTER_PATH } from '@simple-module-py/ui/lib/auth-routes';
import { AuthField } from './AuthField';

export interface OAuthProvider {
  name: string;
  display_name: string;
}

interface LoginFormProps {
  email: string;
  onEmailChange: (next: string) => void;
  password: string;
  onPasswordChange: (next: string) => void;
  remember: boolean;
  onRememberChange: (next: boolean) => void;
  /** How long "keep me signed in" actually keeps you, per settings. */
  rememberDays: number;
  error: string | null;
  loading: boolean;
  onSubmit: (event: React.FormEvent) => void;
  allowSignup: boolean;
  oauthProviders: OAuthProvider[];
}

/**
 * The sign-in card's contents.
 *
 * Split out of the page so the page holds only the request and the two states
 * it can end in — the form, and the "Waiting on you" card an unverified
 * account gets instead.
 */
export function LoginForm({
  email,
  onEmailChange,
  password,
  onPasswordChange,
  remember,
  onRememberChange,
  rememberDays,
  error,
  loading,
  onSubmit,
  allowSignup,
  oauthProviders,
}: LoginFormProps) {
  const { t } = useT();

  return (
    <>
      <h1 className="text-[26px] font-bold tracking-tight text-foreground font-[var(--font-display)] sm:text-[28px]">
        {t(keys.users.login.heading)}
      </h1>
      <p className="mt-1.5 mb-6 text-sm text-muted-foreground">{t(keys.users.login.subtitle)}</p>

      <form onSubmit={onSubmit} className="space-y-3.5">
        <AuthField htmlFor="email" label={t(keys.users.common.email)}>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            placeholder={t(keys.users.common.email_placeholder)}
            required
            autoComplete="email"
          />
        </AuthField>

        <AuthField
          htmlFor="password"
          label={t(keys.users.common.password)}
          action={
            <a
              href="/users/forgot-password"
              className="text-[12.5px] font-medium text-primary-700 hover:text-primary-800"
            >
              {t(keys.users.login.forgot_link)}
            </a>
          }
        >
          <PasswordInput
            id="password"
            value={password}
            onChange={(e) => onPasswordChange(e.target.value)}
            required
            autoComplete="current-password"
            showLabel={t(keys.users.common.show_password)}
            hideLabel={t(keys.users.common.hide_password)}
          />
        </AuthField>

        <div className="flex items-center gap-2.5 pt-0.5">
          <Checkbox
            id="remember"
            checked={remember}
            onCheckedChange={(next) => onRememberChange(next === true)}
          />
          <Label htmlFor="remember" className="text-[13.5px] font-normal text-foreground">
            {t(keys.users.login.remember_me, { days: rememberDays })}
          </Label>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" size="lg" className="w-full max-lg:min-h-11" disabled={loading}>
          {loading ? t(keys.users.login.submitting) : t(keys.users.login.submit)}
        </Button>
      </form>

      {oauthProviders.length > 0 && (
        <div className="mt-5 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <span className="h-px flex-1 bg-border" />
            <span className="text-[12.5px] text-muted-foreground">
              {t(keys.users.login.divider_or)}
            </span>
            <span className="h-px flex-1 bg-border" />
          </div>
          {oauthProviders.map((provider) => (
            <Button
              key={provider.name}
              type="button"
              variant="outline"
              size="lg"
              asChild
              className="max-lg:min-h-11"
            >
              <a href={`/api/users/auth/${provider.name}/login`}>
                {t(keys.users.login.continue_with, { name: provider.display_name })}
              </a>
            </Button>
          ))}
        </div>
      )}

      <p className="mt-5 text-center text-[13.5px] text-muted-foreground">
        {allowSignup ? (
          <>
            {t(keys.users.login.no_account)}{' '}
            <a
              href={REGISTER_PATH}
              className="font-medium text-primary-700 hover:text-primary-800"
            >
              {t(keys.users.login.sign_up)}
            </a>{' '}
            {t(keys.users.login.no_account_suffix)}
          </>
        ) : (
          t(keys.users.login.no_account_invite_only)
        )}
      </p>
    </>
  );
}
