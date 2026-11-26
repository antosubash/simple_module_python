import { cn } from '@simple-module-py/ui/lib/utils';
import { Switch as SwitchPrimitive } from 'radix-ui';
import type * as React from 'react';

function Switch({
  className,
  size = 'default',
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root> & {
  size?: 'sm' | 'default';
}) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      data-size={size}
      className={cn(
        'peer group/switch inline-flex shrink-0 items-center justify-center rounded-full transition-all outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 max-lg:min-h-11 max-lg:min-w-11 pointer-coarse:min-h-11 pointer-coarse:min-w-11',
        className,
      )}
      {...props}
    >
      {/* Keep the track compact inside the larger touch target. */}
      <span
        data-slot="switch-track"
        className="pointer-events-none inline-flex shrink-0 items-center rounded-full border border-transparent shadow-xs group-focus-visible/switch:border-ring group-data-[size=default]/switch:h-[1.15rem] group-data-[size=default]/switch:w-8 group-data-[size=sm]/switch:h-3.5 group-data-[size=sm]/switch:w-6 group-data-[state=checked]/switch:bg-primary group-data-[state=unchecked]/switch:bg-input dark:group-data-[state=unchecked]/switch:bg-input/80"
      >
        <SwitchPrimitive.Thumb
          data-slot="switch-thumb"
          className="pointer-events-none block rounded-full bg-background ring-0 transition-transform group-data-[size=default]/switch:size-4 group-data-[size=sm]/switch:size-3 data-[state=checked]:translate-x-[calc(100%-2px)] data-[state=unchecked]:translate-x-0 dark:data-[state=checked]:bg-primary-foreground dark:data-[state=unchecked]:bg-foreground"
        />
      </span>
    </SwitchPrimitive.Root>
  );
}

export { Switch };
