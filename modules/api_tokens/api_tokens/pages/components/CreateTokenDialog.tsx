import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Checkbox } from '@simple-module-py/ui/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@simple-module-py/ui/components/ui/dialog';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@simple-module-py/ui/components/ui/native-select';
import { type FormEvent, useId, useState } from 'react';
import type { CreatePayload } from '../types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** `service` adds the role picker and changes the copy. */
  variant: 'personal' | 'service';
  scopes: string[];
  roles?: string[];
  expiryPresets: number[];
  busy: boolean;
  /** Resolves true when the token was created, so the form can reset. */
  onSubmit: (payload: CreatePayload) => Promise<boolean>;
}

function toggle(list: string[], value: string, on: boolean): string[] {
  return on ? [...list, value] : list.filter((v) => v !== value);
}

function CheckList({
  idPrefix,
  options,
  selected,
  onChange,
}: {
  idPrefix: string;
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <div className="max-h-48 space-y-2 overflow-y-auto rounded-md border p-3">
      {options.map((option) => {
        const id = `${idPrefix}-${option}`;
        return (
          <div key={option} className="flex items-center gap-2">
            <Checkbox
              id={id}
              checked={selected.includes(option)}
              onCheckedChange={(on) => onChange(toggle(selected, option, on === true))}
            />
            <Label htmlFor={id} className="font-mono text-xs font-normal">
              {option}
            </Label>
          </div>
        );
      })}
    </div>
  );
}

export function CreateTokenDialog({
  open,
  onOpenChange,
  variant,
  scopes,
  roles = [],
  expiryPresets,
  busy,
  onSubmit,
}: Props) {
  const { t } = useT();
  const id = useId();
  const [name, setName] = useState('');
  const [chosenScopes, setChosenScopes] = useState<string[]>([]);
  const [chosenRoles, setChosenRoles] = useState<string[]>([]);
  const [days, setDays] = useState<number>(expiryPresets[Math.min(1, expiryPresets.length - 1)]);
  const isService = variant === 'service';

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const payload: CreatePayload = {
      name: name.trim(),
      scopes: chosenScopes,
      expires_in_days: days,
      ...(isService ? { roles: chosenRoles } : {}),
    };
    if (await onSubmit(payload)) {
      setName('');
      setChosenScopes([]);
      setChosenRoles([]);
    }
  }

  const canSubmit = name.trim().length > 0 && chosenScopes.length > 0 && !busy;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {isService
                ? t(keys.api_tokens.form.create_service_title)
                : t(keys.api_tokens.form.create_title)}
            </DialogTitle>
            <DialogDescription>
              {isService
                ? t(keys.api_tokens.form.create_service_description)
                : t(keys.api_tokens.form.create_description)}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor={`${id}-name`}>{t(keys.api_tokens.form.name)}</Label>
            <Input
              id={`${id}-name`}
              value={name}
              maxLength={100}
              placeholder={t(keys.api_tokens.form.name_placeholder)}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>

          <div className="space-y-2">
            <Label>{t(keys.api_tokens.form.scopes)}</Label>
            <p className="text-xs text-muted-foreground">{t(keys.api_tokens.form.scopes_hint)}</p>
            <CheckList
              idPrefix={`${id}-scope`}
              options={scopes}
              selected={chosenScopes}
              onChange={setChosenScopes}
            />
          </div>

          {isService && (
            <div className="space-y-2">
              <Label>{t(keys.api_tokens.form.roles)}</Label>
              <p className="text-xs text-muted-foreground">{t(keys.api_tokens.form.roles_hint)}</p>
              {roles.length > 0 ? (
                <CheckList
                  idPrefix={`${id}-role`}
                  options={roles}
                  selected={chosenRoles}
                  onChange={setChosenRoles}
                />
              ) : (
                <p className="text-sm text-muted-foreground">{t(keys.api_tokens.form.no_roles)}</p>
              )}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor={`${id}-expiry`}>{t(keys.api_tokens.form.expiry)}</Label>
            <NativeSelect
              id={`${id}-expiry`}
              value={String(days)}
              onChange={(e) => setDays(Number(e.target.value))}
            >
              {expiryPresets.map((preset) => (
                <NativeSelectOption key={preset} value={String(preset)}>
                  {t(keys.api_tokens.form.days, { count: preset })}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t(keys.api_tokens.form.cancel)}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t(keys.api_tokens.form.submit)}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
