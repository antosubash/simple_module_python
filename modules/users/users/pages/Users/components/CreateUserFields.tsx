import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { Lock, Mail } from 'lucide-react';

interface Props {
  email: string;
  fullName: string;
  password: string;
  onEmailChange: (value: string) => void;
  onFullNameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
}

export function CreateUserFields({
  email,
  fullName,
  password,
  onEmailChange,
  onFullNameChange,
  onPasswordChange,
}: Props) {
  const { t } = useT();
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="email" className="text-sm font-medium text-muted-foreground">
          {t(keys.users.common.email)} <span className="text-destructive">*</span>
        </Label>
        <div className="relative">
          <Mail className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            placeholder={t(keys.users.create_fields.email_placeholder)}
            required
            autoComplete="off"
            className="pl-9"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="full_name" className="text-sm font-medium text-muted-foreground">
          {t(keys.users.create_fields.full_name_optional)}
        </Label>
        <Input
          id="full_name"
          type="text"
          value={fullName}
          onChange={(e) => onFullNameChange(e.target.value)}
          placeholder={t(keys.users.create_fields.name_placeholder)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
          {t(keys.users.common.password)} <span className="text-destructive">*</span>
        </Label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => onPasswordChange(e.target.value)}
            placeholder={t(keys.users.create_fields.password_placeholder)}
            required
            autoComplete="new-password"
            className="pl-9"
          />
        </div>
        <p className="text-xs text-muted-foreground">{t(keys.users.create_fields.password_hint)}</p>
      </div>
    </>
  );
}
