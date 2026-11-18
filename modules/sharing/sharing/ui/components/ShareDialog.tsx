import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@simple-module-py/ui/components/ui/dialog';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { NativeSelect } from '@simple-module-py/ui/components/ui/native-select';
import { useId, useState } from 'react';
import { MIN_QUERY, useShares } from '../hooks/useShares';

export interface ShareRole {
  value: string;
  label: string;
}
export interface ShareDialogProps {
  resourceType: string;
  resourceId: string;
  /** Translated labels for the resource's custom share_roles. Defaults to view/edit. */
  roles?: readonly ShareRole[];
}

export function ShareDialog(props: ShareDialogProps) {
  // A different resource gets a fresh dialog, including its selected role.
  return <ResourceShareDialog key={`${props.resourceType}/${props.resourceId}`} {...props} />;
}

function ResourceShareDialog({ resourceType, resourceId, roles }: ShareDialogProps) {
  const { t } = useT();
  const id = useId();
  const options = roles ?? [
    { value: 'view', label: t(keys.sharing.dialog.role_view) },
    { value: 'edit', label: t(keys.sharing.dialog.role_edit) },
  ];
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(options[0]?.value ?? '');
  const role = options.some((option) => option.value === selected) ? selected : options[0]?.value;
  const state = useShares(resourceType, resourceId, open);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!state.pending) setOpen(next);
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" variant="outline">
          {t(keys.sharing.dialog.button)}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>{t(keys.sharing.dialog.title)}</DialogTitle>
          <DialogDescription>{t(keys.sharing.dialog.description)}</DialogDescription>
        </DialogHeader>
        <section className="space-y-2" aria-label={t(keys.sharing.dialog.current)}>
          <h3 className="text-sm font-medium">{t(keys.sharing.dialog.current)}</h3>
          {state.loading ? (
            <p role="status">{t(keys.sharing.dialog.loading)}</p>
          ) : state.shares.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t(keys.sharing.dialog.none)}</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {state.shares.map((share) => {
                const name = share.subject_label ?? share.subject_id;
                return (
                  <li
                    key={share.id}
                    className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                  >
                    <div className="min-w-0 break-words">
                      <p>{name}</p>
                      <p className="text-muted-foreground">
                        {options.find((option) => option.value === share.role)?.label ?? share.role}
                      </p>
                      {share.expired && <p>{t(keys.sharing.list.expired)}</p>}
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={state.pending}
                      aria-label={t(keys.sharing.dialog.revoke_for, { name })}
                      onClick={() => void state.revoke(share)}
                    >
                      {t(keys.sharing.dialog.revoke)}
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
        <section className="space-y-3">
          <div className="grid gap-2">
            <Label htmlFor={`${id}-search`}>{t(keys.sharing.dialog.search_label)}</Label>
            <Input
              id={`${id}-search`}
              type="search"
              value={state.query}
              placeholder={t(keys.sharing.dialog.search_placeholder)}
              onChange={(event) => state.setQuery(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor={`${id}-role`}>{t(keys.sharing.dialog.role)}</Label>
            <NativeSelect
              id={`${id}-role`}
              value={role ?? ''}
              disabled={!options.length}
              onChange={(event) => setSelected(event.target.value)}
            >
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div aria-live="polite">
            {state.tooShort ? (
              <p className="text-sm text-muted-foreground">
                {t(keys.sharing.dialog.search_min, { min: MIN_QUERY })}
              </p>
            ) : state.searching ? (
              <p>{t(keys.sharing.dialog.loading)}</p>
            ) : state.candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {t(keys.sharing.dialog.no_candidates)}
              </p>
            ) : (
              <ul className="max-h-48 divide-y overflow-auto rounded-md border">
                {state.candidates.map((candidate) => (
                  <li
                    key={candidate.id}
                    className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                  >
                    <div className="min-w-0 break-words">
                      <p>{candidate.display_name}</p>
                      <p className="text-xs text-muted-foreground">{candidate.email}</p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      disabled={state.pending || state.loading || !role}
                      onClick={() => role && void state.grant(candidate, role)}
                    >
                      {t(keys.sharing.dialog.grant)}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
        {state.error && (
          <p className="text-sm text-destructive" role="alert">
            {state.error}
          </p>
        )}
        <DialogClose asChild>
          <Button type="button" variant="outline" disabled={state.pending}>
            {t(keys.sharing.dialog.close)}
          </Button>
        </DialogClose>
      </DialogContent>
    </Dialog>
  );
}
