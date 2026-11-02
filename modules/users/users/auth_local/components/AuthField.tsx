import { Label } from '@simple-module-py/ui/components/ui/label';
import type React from 'react';

interface AuthFieldProps {
  /** Matches the control's `id` so clicking the label focuses it. */
  htmlFor: string;
  label: string;
  /** Right-aligned on the label's baseline — the deck puts "Forgot password?" here. */
  action?: React.ReactNode;
  /** Field-level message, shown under the control in the destructive tone. */
  error?: string | null;
  children: React.ReactNode;
}

/**
 * One labelled control on an auth card.
 *
 * The six public screens repeat the same three-part shape — label row, input,
 * optional inline error — and the deck puts an action on the label's baseline
 * for exactly one field. Kept in one place so a field-level error looks the
 * same on register, reset and invite instead of drifting into three variants.
 */
export function AuthField({ htmlFor, label, action, error, children }: AuthFieldProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <Label htmlFor={htmlFor} className="text-[13px] font-medium text-foreground">
          {label}
        </Label>
        {action}
      </div>
      {children}
      {error && <p className="text-[12.5px] text-destructive">{error}</p>}
    </div>
  );
}
