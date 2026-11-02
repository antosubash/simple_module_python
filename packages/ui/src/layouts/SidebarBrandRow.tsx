import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { X } from 'lucide-react';
import { BrandingMark } from '../components/BrandingMark';
import { SIDEBAR_ICON_FOCUS, type SidebarTheme } from './sidebar-theme';

interface SidebarBrandRowProps {
  theme: SidebarTheme;
  appName: string;
  logoUrl: string | null;
  homeUrl: string;
  onClose: () => void;
}

/**
 * Drawer header — ✕ then the app name, per the deck's phone frame. On lg the
 * close button is gone and this is the 64px brand row.
 */
export function SidebarBrandRow({
  theme,
  appName,
  logoUrl,
  homeUrl,
  onClose,
}: SidebarBrandRowProps) {
  const { t } = useT();
  return (
    <div className="h-14 lg:h-16 flex items-center gap-3 px-4 lg:px-5 border-b border-white/[0.06]">
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onClose}
        aria-label={t(keys.ui.sidebar.close)}
        className={`lg:hidden min-h-11 min-w-11 -ml-2 text-sidebar-icon-muted hover:text-white hover:bg-white/10 ${SIDEBAR_ICON_FOCUS}`}
      >
        <X aria-hidden="true" className="h-5 w-5" strokeWidth={1.8} />
      </Button>
      <Link href={homeUrl} className="flex items-center gap-2.5 group">
        <BrandingMark
          appName={appName}
          logoUrl={logoUrl}
          accentColor={theme.accentColor}
          size="md"
        />
      </Link>
    </div>
  );
}
