import { Link } from '@inertiajs/react';

export type ModuleHealth = '' | 'healthy' | 'degraded' | 'unhealthy';

interface Props {
  /** Package directory — the mono label the deck puts on the tile. */
  name: string;
  /** Display name, shown as the tooltip when the package name is truncated. */
  displayName: string;
  /** The module's own screen. Empty, or not in the user's menus, renders inert. */
  url: string;
  health: ModuleHealth;
  /** False when the module ships no screen this user is allowed to open. */
  reachable: boolean;
  /** "loaded · healthy", "loaded · no checks", … */
  statusLabel: string;
  /** "Open" or "No view". */
  actionLabel: string;
}

const DOT: Record<ModuleHealth, string> = {
  '': 'bg-muted-foreground/40',
  healthy: 'bg-primary',
  degraded: 'bg-amber-500',
  unhealthy: 'bg-red-500',
};

const BASE = 'flex w-full flex-col gap-2 rounded-xl border p-3.5 text-left';

/**
 * One installed module: name, health dot, and where it goes.
 *
 * A degraded module is tinted rather than merely dotted — the dot alone is an
 * 8px cue in a grid of twelve tiles, which is exactly the sort of thing you
 * miss on the screen you are scanning for problems.
 */
export function ModuleTile({
  name,
  displayName,
  url,
  health,
  reachable,
  statusLabel,
  actionLabel,
}: Props) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <code className="min-w-0 truncate font-mono text-[13.5px] font-medium" title={displayName}>
          {name}
        </code>
        <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[health]}`} aria-hidden="true" />
      </div>
      {/* Four tiles per row at 390px leaves no width for a second line: the
          deck's phone frame is the mono name and the health dot, nothing else. */}
      <div className="hidden items-center justify-between gap-2 sm:flex">
        <span className="min-w-0 truncate text-[11.5px] text-muted-foreground">{statusLabel}</span>
        <span
          className={`shrink-0 text-[11.5px] font-medium ${
            reachable ? 'text-primary-700' : 'text-muted-foreground'
          }`}
        >
          {actionLabel}
        </span>
      </div>
    </>
  );

  const tint =
    health === 'degraded'
      ? 'border-amber-200 bg-amber-50/60'
      : health === 'unhealthy'
        ? 'border-red-200 bg-red-50/60'
        : 'border-border bg-card';

  // A module with no screen — or one this user cannot open — stays a plain
  // tile. Linking it anyway would hand the user a guaranteed 403.
  if (!reachable) {
    return <div className={`${BASE} ${tint} cursor-not-allowed opacity-55`}>{body}</div>;
  }

  return (
    <Link href={url} className={`${BASE} ${tint} transition-colors hover:border-primary`}>
      {body}
    </Link>
  );
}
