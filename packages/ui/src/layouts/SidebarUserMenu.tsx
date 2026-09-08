import { Link } from '@inertiajs/react';
import { Avatar, AvatarFallback } from '@simple-module-py/ui/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@simple-module-py/ui/components/ui/dropdown-menu';
import { ChevronsUpDown } from 'lucide-react';
import type React from 'react';
import { NavIcon } from '../components/NavIcon';
import { initials } from '../lib/initials';
import { isPostMenuItem, type MenuItem } from '../types';

interface SidebarUserMenuProps {
  user: { name: string; email: string; roles: string[] };
  items: MenuItem[];
  /** Sidebar theme fragments supplied by the owning layout. */
  hoverBg: string;
  mutedTextClass: string;
  onNavigate: () => void;
}

/**
 * Avatar row at the foot of the sidebar, opening Profile / Logout / etc.
 *
 * Split out of `SidebarLayout` to keep that file within the repo's 300-line
 * cap; it is a self-contained piece of the shell with no shared state.
 */
export function SidebarUserMenu({
  user,
  items,
  hoverBg,
  mutedTextClass,
  onNavigate,
}: SidebarUserMenuProps): React.ReactElement {
  // UserContext.from_user defaults ``name`` to ``email`` when no full_name is
  // set, so guard against rendering the email twice.
  const hasDistinctName = user.name && user.name !== user.email;

  const identity = (muted: string) =>
    hasDistinctName ? (
      <>
        <p className="truncate text-sm font-medium">{user.name}</p>
        <p className={`truncate text-xs ${muted}`}>{user.email}</p>
      </>
    ) : (
      <p className="truncate text-sm font-medium">{user.email}</p>
    );

  return (
    <div className="border-t border-white/[0.06] px-3 py-3">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={`flex w-full min-h-11 lg:min-h-0 items-center gap-3 rounded-lg px-2 py-2 text-left ${hoverBg} transition-colors`}
          >
            {/* Two letters on a neutral surface, per the deck — a coloured
                ring read as a status indicator the avatar does not carry. */}
            <Avatar>
              <AvatarFallback className="bg-white/10 text-xs font-bold text-white">
                {initials(user.name, user.email)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1 text-white">{identity(mutedTextClass)}</div>
            <ChevronsUpDown className={`h-4 w-4 shrink-0 ${mutedTextClass}`} aria-hidden="true" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="start" className="w-56">
          <DropdownMenuLabel className="font-normal">
            {identity('text-muted-foreground')}
          </DropdownMenuLabel>
          {items.length > 0 && <DropdownMenuSeparator />}
          {items.map((item) => (
            <DropdownMenuItem key={item.url} asChild onSelect={onNavigate}>
              <Link
                href={item.url}
                method={isPostMenuItem(item) ? 'post' : 'get'}
                as={isPostMenuItem(item) ? 'button' : 'a'}
                className="flex w-full items-center gap-2"
              >
                <NavIcon name={item.icon} />
                {item.label}
              </Link>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
