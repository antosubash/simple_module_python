import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { ChevronLeft, Menu } from 'lucide-react';
import type React from 'react';
import { type PageMobileAction, usePageChrome } from '../components/page-heading';
import { initials } from '../lib/initials';
import type { SidebarTheme } from './sidebar-theme';
import { SIDEBAR_ICON_FOCUS } from './sidebar-theme';

interface MobileBarProps {
  theme: SidebarTheme;
  /** Shown while no page has reported a title yet. */
  appName: string;
  currentUrl: string;
  user?: { name: string; email: string } | null;
  onOpen: () => void;
}

// 44px is the phone hit-target floor; the bar itself is 56px, so the controls
// have room to meet it without the row growing.
const TAP = 'min-h-11 min-w-11';

function ActionSlot({ action }: { action: PageMobileAction }) {
  const className = `${TAP} inline-flex items-center justify-center rounded-lg px-2 text-[13.5px] font-medium text-primary-300 transition-colors hover:text-white ${SIDEBAR_ICON_FOCUS}`;
  if (action.href) {
    return (
      <Link href={action.href} className={className}>
        {action.label}
      </Link>
    );
  }
  return (
    <button type="button" onClick={action.onClick} className={className}>
      {action.label}
    </button>
  );
}

/**
 * The bar above every app screen on a phone.
 *
 * Split out of `SidebarLayout` to keep that file within the repo's 300-line
 * cap. It carries what the deck's phone frames carry and nothing else: a way
 * back (the drawer, or the page's own parent), the page's name, and the one
 * action that page considers primary. The brand lives in the drawer header —
 * repeating it here spent the only line of text on the screen restating what
 * the user already knows they are inside of.
 */
export function MobileBar({
  theme,
  appName,
  currentUrl,
  user,
  onOpen,
}: MobileBarProps): React.ReactElement {
  const { t } = useT();
  const chrome = usePageChrome(currentUrl);
  const action = chrome?.mobileAction;

  return (
    <div
      className={`sticky top-0 z-40 flex h-[var(--app-chrome-h)] items-center gap-3 ${theme.sidebarBg} px-4 lg:hidden`}
    >
      {chrome?.back ? (
        <Link
          href={chrome.back}
          aria-label={t(keys.ui.sidebar.back)}
          className={`${TAP} -ml-2 inline-flex items-center justify-center rounded-md text-sidebar-icon transition-colors hover:bg-white/10 hover:text-white ${SIDEBAR_ICON_FOCUS}`}
        >
          <ChevronLeft aria-hidden="true" className="h-6 w-6" strokeWidth={1.8} />
        </Link>
      ) : (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onOpen}
          aria-label={t(keys.ui.sidebar.open)}
          className={`${TAP} -ml-2 text-sidebar-icon hover:bg-white/10 hover:text-white ${SIDEBAR_ICON_FOCUS}`}
        >
          <Menu aria-hidden="true" className="h-6 w-6" strokeWidth={1.8} />
        </Button>
      )}

      <span
        className={
          chrome?.mono
            ? 'truncate font-mono text-sm text-white'
            : 'truncate font-[var(--font-display)] text-[15px] font-bold text-white'
        }
      >
        {chrome?.title ?? appName}
      </span>

      <div className="ml-auto flex items-center">
        {action ? (
          <ActionSlot action={action} />
        ) : (
          user && (
            <span
              aria-hidden="true"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-[11px] font-bold text-white"
            >
              {initials(user.name, user.email)}
            </span>
          )
        )}
      </div>
    </div>
  );
}
