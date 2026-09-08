import type { LucideIcon } from 'lucide-react';
import type React from 'react';

/** Which outcome the card reports — picks the tile tint. */
export type AuthStateTone = 'primary' | 'amber' | 'destructive' | 'neutral';

const TILE_TONE: Record<AuthStateTone, string> = {
  primary: 'bg-primary-600/10 text-primary-700',
  amber: 'bg-amber-50 text-amber-700',
  destructive: 'bg-red-50 text-red-700',
  neutral: 'bg-secondary text-muted-foreground',
};

interface AuthStateCardProps {
  icon: LucideIcon;
  /** Extra classes for the glyph — the pending state spins its spinner. */
  iconClassName?: string;
  tone: AuthStateTone;
  title: string;
  /** A node, not a string: some states put the address in bold mid-sentence. */
  description?: React.ReactNode;
  /** Buttons or links under the copy. */
  children?: React.ReactNode;
}

/**
 * The "one outcome, stated plainly" card: tinted tile, heading, a sentence,
 * one action.
 *
 * Every terminal state across verify, reset and invite is this shape, and the
 * tint is the fastest read of which one it is — emerald for done, amber for
 * "do it again", red for "this is gone". Content is left-aligned rather than
 * centred so it lines up with the forms on the sibling screens.
 */
export function AuthStateCard({
  icon: Icon,
  iconClassName,
  tone,
  title,
  description,
  children,
}: AuthStateCardProps) {
  return (
    <div className="flex flex-col items-start gap-4">
      <span
        className={`inline-flex h-[46px] w-[46px] items-center justify-center rounded-[13px] ${TILE_TONE[tone]}`}
      >
        <Icon className={`h-[21px] w-[21px] ${iconClassName ?? ''}`} aria-hidden="true" />
      </span>
      <h1 className="text-[21px] font-bold tracking-tight text-foreground font-display">{title}</h1>
      {description && (
        <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
      )}
      {children}
    </div>
  );
}
