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
  return (
    <>
      <div className="space-y-2">
        <Label htmlFor="email" className="text-sm font-medium text-muted-foreground">
          Email <span className="text-destructive">*</span>
        </Label>
        <div className="relative">
          <Mail className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => onEmailChange(e.target.value)}
            placeholder="teammate@example.com"
            required
            autoComplete="off"
            className="pl-9"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="full_name" className="text-sm font-medium text-muted-foreground">
          Full name (optional)
        </Label>
        <Input
          id="full_name"
          type="text"
          value={fullName}
          onChange={(e) => onFullNameChange(e.target.value)}
          placeholder="Jane Doe"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
          Password <span className="text-destructive">*</span>
        </Label>
        <div className="relative">
          <Lock className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => onPasswordChange(e.target.value)}
            required
            autoComplete="new-password"
            className="pl-9"
          />
        </div>
        <p className="text-xs text-muted-foreground">
          The account is active and verified immediately — share the password securely.
        </p>
      </div>
    </>
  );
}
