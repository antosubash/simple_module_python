import { Input } from '@simple-module-py/ui/components/ui/input';
import { cn } from '@simple-module-py/ui/lib/utils';
import type React from 'react';
import { useState } from 'react';

interface PasswordInputProps extends Omit<React.ComponentProps<typeof Input>, 'type'> {
  showLabel: string;
  hideLabel: string;
}

/**
 * A password field that can be read back.
 *
 * Typing a password blind is where sign-up attempts go to die, and the reveal
 * is a word rather than an eye icon because "Show"/"Hide" says what will
 * happen — an eye with a line through it does not tell you which state you are
 * in. The labels are passed in already translated so this stays a primitive.
 */
export function PasswordInput({ showLabel, hideLabel, className, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <Input {...props} type={visible ? 'text' : 'password'} className={cn('pr-16', className)} />
      <button
        type="button"
        onClick={() => setVisible((prev) => !prev)}
        // Centred and out of flow, so `min-h-11` buys a 44px phone hit target
        // without making the field itself taller than every other input.
        className="absolute top-1/2 right-0 flex h-full -translate-y-1/2 items-center px-3 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground max-lg:min-h-11"
      >
        {visible ? hideLabel : showLabel}
      </button>
    </div>
  );
}
