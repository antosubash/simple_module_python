import { Link } from '@inertiajs/react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@simple-module-py/ui/components/ui/tooltip';
import type React from 'react';
import { NavIcon } from '../components/NavIcon';
import type { MenuItem } from '../types';
import { AdminSectionLink } from './AdminSectionLink';
import type { SidebarTheme } from './sidebar-theme';

// Phones get 44px rows; the desktop sidebar keeps the deck's tighter 40px.
const NAV_ROW =
  'flex items-center gap-3 min-h-11 lg:min-h-0 px-3 py-2.5 rounded-lg text-[15px] font-medium transition-all duration-150';

function groupMenuItems(items: MenuItem[]): { group: string; items: MenuItem[] }[] {
  const groups: { group: string; items: MenuItem[] }[] = [];
  const indexByGroup = new Map<string, number>();
  for (const item of items) {
    const key = item.group ?? '';
    let idx = indexByGroup.get(key);
    if (idx === undefined) {
      idx = groups.length;
      indexByGroup.set(key, idx);
      groups.push({ group: key, items: [] });
    }
    groups[idx].items.push(item);
  }
  return groups;
}

interface SidebarNavProps {
  menuItems: MenuItem[];
  adminItems: MenuItem[];
  active: MenuItem | null | undefined;
  theme: SidebarTheme;
  /** The app sidebar ends with a link into the admin section; the admin one does not. */
  showAdminLink: boolean;
  onNavigate: () => void;
  /** Rendered after the last group, inside the scroll area. */
  children?: React.ReactNode;
}

/** The sidebar's grouped navigation list. */
export function SidebarNav({
  menuItems,
  adminItems,
  active,
  theme,
  showAdminLink,
  onNavigate,
  children,
}: SidebarNavProps) {
  return (
    <nav className="flex-1 px-3 py-4 overflow-y-auto">
      {groupMenuItems(menuItems).map((group, groupIndex) => (
        <div
          key={group.group || `__ungrouped_${groupIndex}`}
          className={groupIndex === 0 ? 'space-y-0.5' : 'mt-4 space-y-0.5'}
        >
          {group.group && (
            <div
              className={`px-3 pb-1.5 text-[11px] font-bold uppercase tracking-[0.09em] ${theme.mutedTextClass}`}
            >
              {group.group}
            </div>
          )}
          {group.items.map((item, index) => {
            const isActive = active?.url === item.url;
            return (
              <Tooltip key={item.url}>
                <TooltipTrigger asChild>
                  <Link
                    href={item.url}
                    onClick={onNavigate}
                    className={`${NAV_ROW} ${isActive ? theme.activeClass : theme.inactiveClass}`}
                    style={{ animationDelay: `${index * 50}ms` }}
                  >
                    {/* No icons on phones: the deck's drawer is a list of
                        names, and the glyphs only crowd a 390px row. */}
                    <NavIcon name={item.icon} className="hidden lg:block w-5 h-5" />
                    {item.label}
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right" className="lg:hidden">
                  {item.label}
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
      ))}
      {showAdminLink && (
        <AdminSectionLink
          adminItems={adminItems}
          className={`min-h-11 lg:min-h-0 ${theme.inactiveClass}`}
          onNavigate={onNavigate}
        />
      )}
      {children}
    </nav>
  );
}
