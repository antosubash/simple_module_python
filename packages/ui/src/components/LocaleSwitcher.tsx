import { usePage } from '@inertiajs/react';
import { useT } from '@simple-module/i18n';
import { Button } from '@simple-module/ui/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@simple-module/ui/components/ui/dropdown-menu';
import { Globe } from 'lucide-react';
import { useRef } from 'react';

/**
 * Static map of locale code -> label in that locale's own language.
 * Picked before the user can read the current UI language, so labels
 * must not depend on t().
 */
const LOCALE_LABELS: Record<string, string> = {
  en: 'English',
  es: 'Español',
  de: 'Deutsch',
  fr: 'Français',
  pt: 'Português',
  ja: '日本語',
  zh: '中文',
  ru: 'Русский',
};

interface I18nSharedProps {
  locale: string;
  supportedLocales: string[];
  messages: Record<string, string>;
}

export function LocaleSwitcher() {
  const page = usePage<{ i18n?: I18nSharedProps }>();
  const i18n = page.props.i18n;
  const formRef = useRef<HTMLFormElement>(null);
  const { t } = useT();

  if (!i18n || i18n.supportedLocales.length <= 1) {
    return null;
  }

  const select = (locale: string) => {
    if (locale === i18n.locale) return;
    const form = formRef.current;
    if (!form) return;
    const input = form.elements.namedItem('locale') as HTMLInputElement | null;
    if (!input) return;
    input.value = locale;
    form.submit();
  };

  return (
    <>
      <form ref={formRef} method="POST" action="/i18n/set-locale" style={{ display: 'none' }}>
        <input type="hidden" name="locale" value="" readOnly />
      </form>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={t('ui.switcher.label')}>
            <Globe />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {i18n.supportedLocales.map((code) => (
            <DropdownMenuItem
              key={code}
              onSelect={() => select(code)}
              data-active={code === i18n.locale}
            >
              {LOCALE_LABELS[code] ?? code}
              {code === i18n.locale && <span className="ml-auto text-xs">✓</span>}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );
}
