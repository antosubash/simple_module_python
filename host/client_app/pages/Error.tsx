import { Link } from '@inertiajs/react';
import { useT } from '@simple-module/i18n';
import { ErrorScreen } from '@simple-module/ui/components/ErrorScreen';
import { Button } from '@simple-module/ui/components/ui/button';

interface Props {
  status: number;
  message: string;
}

function ErrorPage({ status, message }: Props) {
  const { t } = useT();

  const titles: Record<number, string> = {
    403: t('host.error.forbidden_title'),
    404: t('host.error.not_found_title'),
    500: t('host.error.server_error_title'),
  };

  const descriptions: Record<number, string> = {
    403: t('host.error.forbidden_description'),
    404: t('host.error.not_found_description'),
    500: t('host.error.server_error_description'),
  };

  const title = titles[status] || t('host.error.generic_title');
  const description = message || descriptions[status] || t('host.error.generic_description');

  return (
    <ErrorScreen hero={status} title={title} description={description}>
      <Button asChild>
        <Link href="/">{t('host.error.go_home')}</Link>
      </Button>
      <Button variant="outline" onClick={() => window.history.back()}>
        {t('host.error.go_back')}
      </Button>
    </ErrorScreen>
  );
}

export default ErrorPage;
