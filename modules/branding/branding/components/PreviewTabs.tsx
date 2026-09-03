import { keys, useT } from '@simple-module-py/i18n';
import { SegmentedControl } from '@simple-module-py/ui/components/SegmentedControl';
import { Card } from '@simple-module-py/ui/components/ui/card';
import { useState } from 'react';
import { BrandingPreview, type PreviewBrand } from './BrandingPreview';
import { EmailPreview, SignInPreview } from './PreviewSurfaces';

type Surface = 'app' | 'signin' | 'email';

/**
 * Live preview of the three surfaces branding reaches.
 *
 * Tabs rather than three stacked frames: they are alternatives, not a
 * checklist, and stacking them would push the form's own controls off the
 * screen on anything smaller than a desktop.
 */
export function PreviewTabs({ brand }: { brand: PreviewBrand }) {
  const { t } = useT();
  const [surface, setSurface] = useState<Surface>('app');

  return (
    <Card className="flex flex-col overflow-hidden border-border p-0">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <span className="flex-1 text-sm font-bold font-[var(--font-display)]">
          {t(keys.branding.manage.preview_title)}
        </span>
        <SegmentedControl
          value={surface}
          onChange={setSurface}
          size="sm"
          aria-label={t(keys.branding.manage.preview_tabs_label)}
          options={[
            { value: 'app', label: t(keys.branding.manage.preview_tab_app) },
            { value: 'signin', label: t(keys.branding.manage.preview_tab_signin) },
            { value: 'email', label: t(keys.branding.manage.preview_tab_email) },
          ]}
        />
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        {surface === 'app' && <BrandingPreview brand={brand} />}
        {surface === 'signin' && <SignInPreview brand={brand} />}
        {surface === 'email' && <EmailPreview brand={brand} />}
        <p className="text-[12.5px] leading-relaxed text-muted-foreground">
          {t(keys.branding.manage.preview_caption)}
        </p>
      </div>
    </Card>
  );
}
