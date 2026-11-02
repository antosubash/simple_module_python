import { Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { InlineBanner } from '@simple-module-py/ui/components/InlineBanner';
import { TriangleAlert } from 'lucide-react';

const SETTINGS_URL = '/admin/settings/';

/** Warns that the configured mailer cannot deliver, so invite links must be shared by hand. */
export function MailerBanner({ mailerName }: { mailerName: string }) {
  const { t } = useT();
  return (
    // One sentence, as the deck has it — a title/body pair reads as two
    // separate facts when it is really one: which mailer, and what that
    // means for the links. The "Configure SMTP" link ends the sentence
    // rather than sitting right-aligned away from what it refers to.
    <InlineBanner
      icon={TriangleAlert}
      tone="warning"
      align="start"
      title={
        <span className="font-normal">
          {t(keys.users.add_people.mailer_banner_prefix)} <b>{mailerName}</b>{' '}
          {t(keys.users.add_people.mailer_banner_suffix)}{' '}
          {/* The 44px tap area is grown with a pseudo-element: an inline
                link inside a sentence cannot take `min-h-11` without
                stretching the line box around it. */}
          <Link
            href={SETTINGS_URL}
            className="relative font-medium underline max-lg:after:absolute max-lg:after:top-1/2 max-lg:after:left-0 max-lg:after:h-11 max-lg:after:w-full max-lg:after:-translate-y-1/2 max-lg:after:content-['']"
          >
            {t(keys.users.add_people.configure_smtp)}
          </Link>
        </span>
      }
    />
  );
}
