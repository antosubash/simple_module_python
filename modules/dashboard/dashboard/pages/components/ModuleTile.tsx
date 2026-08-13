import { Link } from '@inertiajs/react';
import { Box, ChevronRight } from 'lucide-react';

export type ModuleHealth = '' | 'healthy' | 'degraded' | 'unhealthy';

interface Props {
  name: string;
  /** The module's own screen. Empty, or not in the user's menus, renders inert. */
  url: string;
  health: ModuleHealth;
  /** False when the module ships no screen this user is allowed to open. */
  reachable: boolean;
  healthLabel?: string;
}

const DOT: Record<Exclude<ModuleHealth, ''>, string> = {
  healthy: 'bg-primary',
  degraded: 'bg-amber-500',
  unhealthy: 'bg-red-500',
};

const BASE =
  'flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-left w-full';

export function ModuleTile({ name, url, health, reachable, healthLabel }: Props) {
  const body = (
    <>
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
        <Box className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">{name}</span>
      {health ? (
        <>
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT[health]}`}
            aria-hidden="true"
            title={healthLabel}
          />
          <span className="sr-only">{healthLabel}</span>
        </>
      ) : null}
      {reachable ? (
        <ChevronRight
          className="h-3.5 w-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
          aria-hidden="true"
        />
      ) : null}
    </>
  );

  // A module with no screen — or one this user cannot open — stays a plain
  // tile. Linking it anyway would hand the user a guaranteed 403.
  if (!reachable) {
    return <div className={BASE}>{body}</div>;
  }

  return (
    <Link
      href={url}
      className={`${BASE} group transition-colors hover:border-primary/40 hover:bg-accent`}
    >
      {body}
    </Link>
  );
}
