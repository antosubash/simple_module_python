import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@simple-module-py/ui/components/ui/alert-dialog';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { cn } from '@simple-module-py/ui/lib/utils';
import type { LucideIcon } from 'lucide-react';
import type React from 'react';
import { useEffect, useId, useState } from 'react';

interface ConfirmActionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Tints the icon tile and picks the confirm button's variant. */
  tone?: 'destructive' | 'primary';
  icon: LucideIcon;
  title: React.ReactNode;
  description: React.ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  /** The action is in flight. Passing it at all makes the caller responsible
   *  for closing the dialog — see the note on the confirm button. */
  busy?: boolean;
  /** Type-to-confirm. Matched case-insensitively; gates the confirm button. */
  confirmText?: { expected: string; label: string; placeholder?: string };
  /** Extra detail between the description and the buttons — an args box, a warning. */
  children?: React.ReactNode;
}

const TILE_TONE = {
  destructive: 'bg-red-50 text-red-600',
  primary: 'bg-primary-600/10 text-primary-700',
} as const;

/**
 * The one shape every "are you sure?" in this app takes.
 *
 * Consistency is the point: a destructive confirm should look the same
 * wherever it appears, so a reader learns to slow down at the red tile rather
 * than re-reading each dialog from scratch. Type-to-confirm is here rather
 * than at each call site because the gate is easy to get subtly wrong — an
 * exact-match check that rejects a trailing space trains people to paste
 * blindly, which is the opposite of what the gate is for.
 */
export function ConfirmActionDialog({
  open,
  onOpenChange,
  tone = 'destructive',
  icon: Icon,
  title,
  description,
  confirmLabel,
  cancelLabel,
  onConfirm,
  busy,
  confirmText,
  children,
}: ConfirmActionDialogProps) {
  const inputId = useId();
  const [typed, setTyped] = useState('');

  // Reopening the dialog must re-ask for the confirmation, not inherit the
  // answer someone typed before they cancelled.
  useEffect(() => {
    if (!open) setTyped('');
  }, [open]);

  const matched =
    !confirmText || typed.trim().toLowerCase() === confirmText.expected.trim().toLowerCase();

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        {/* Not AlertDialogMedia: that slot is size-16 and row-spans beside the
            title on desktop, where the deck wants a 40px tile above it. */}
        <AlertDialogHeader className="place-items-start gap-2 text-left">
          <span
            className={cn(
              'inline-flex h-10 w-10 items-center justify-center rounded-xl',
              TILE_TONE[tone],
            )}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>
        {children}
        {confirmText && (
          <div className="space-y-1.5">
            <Label htmlFor={inputId}>{confirmText.label}</Label>
            <Input
              id={inputId}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={confirmText.placeholder}
              autoComplete="off"
              className="font-mono"
            />
          </div>
        )}
        <AlertDialogFooter>
          {/* The shared Button is h-9; a confirm — destructive most of all — is
              the most primary control on the screen, so it clears 44px on phones.
              It has to happen here: this component exposes no className. */}
          <AlertDialogCancel className="max-lg:min-h-11">{cancelLabel}</AlertDialogCancel>
          <AlertDialogAction
            variant={tone === 'destructive' ? 'destructive' : 'default'}
            disabled={busy === true || !matched}
            // Radix closes the dialog on this click, which would hide the busy
            // state a caller passing `busy` is about to enter — the prop was
            // inert for exactly that reason. Preventing the default leaves the
            // dialog's fate to `open`, so callers that never mention `busy`
            // are closed here instead of being left with a stuck dialog.
            onClick={(event) => {
              event.preventDefault();
              onConfirm();
              if (busy === undefined) onOpenChange(false);
            }}
            className="max-lg:min-h-11"
          >
            {confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
