import { router } from '@inertiajs/react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@simple-module-py/ui/components/ui/command';
import { Search } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { MenuItem } from '../types';
import { NavIcon } from './NavIcon';

interface CommandPaletteProps {
  /** Sidebar entries, already filtered to what this user may see. */
  navItems: MenuItem[];
  /** Profile / log out / anything else the user menu offers. */
  accountItems: MenuItem[];
}

function groupOf(item: MenuItem): string {
  return item.group || 'Navigation';
}

/**
 * ⌘K over everything the sidebar can reach.
 *
 * Built from the same menu registry the sidebar renders, so it inherits the
 * permission filtering already applied to those entries and cannot offer a
 * destination the user would be 403'd from. Account actions come last: it is
 * the keyboard route to log out, which otherwise lives only behind the avatar
 * dropdown.
 */
export function CommandPalette({ navItems, accountItems }: CommandPaletteProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const go = (item: MenuItem) => {
    setOpen(false);
    // Menu entries carry their own method — logging out is a POST, and
    // visiting it with a GET would silently do nothing.
    if (item.method === 'post') router.post(item.url);
    else router.visit(item.url);
  };

  const groups: Record<string, MenuItem[]> = {};
  for (const item of navItems) {
    const key = groupOf(item);
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
      >
        <Search className="size-3.5" aria-hidden="true" />
        <span>Search</span>
        <kbd className="ml-1 font-mono text-[10px] tracking-wide opacity-70">⌘K</kbd>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Search"
        description="Jump to any page you have access to."
      >
        <CommandInput placeholder="Jump to…" />
        <CommandList>
          <CommandEmpty>Nothing matches that.</CommandEmpty>
          {Object.entries(groups).map(([group, items]) => (
            <CommandGroup key={group} heading={group}>
              {items.map((item) => (
                <CommandItem
                  key={item.url}
                  value={`${group} ${item.label}`}
                  onSelect={() => go(item)}
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
          {accountItems.length > 0 && (
            <CommandGroup heading="Account">
              {accountItems.map((item) => (
                <CommandItem
                  key={item.url}
                  value={`account ${item.label}`}
                  onSelect={() => go(item)}
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </CommandDialog>
    </>
  );
}
