import { Head, Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { ErrorScreen } from '@simple-module-py/ui/components/ErrorScreen';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Home, LifeBuoy } from 'lucide-react';

interface Props {
  status: number;
  message: string;
}

function ErrorPage({ status, message }: Props) {
  const { t } = useT();

  const titles: Record<number, string> = {
    403: t(keys.host.error.forbidden_title),
    404: t(keys.host.error.not_found_title),
    500: t(keys.host.error.server_error_title),
  };

  const descriptions: Record<number, string> = {
    403: t(keys.host.error.forbidden_description),
    404: t(keys.host.error.not_found_description),
    500: t(keys.host.error.server_error_description),
  };

  const accents: Record<number, 'primary' | 'warning' | 'destructive'> = {
    403: 'warning',
    404: 'primary',
    500: 'destructive',
  };

  const title = titles[status] || t(keys.host.error.generic_title);
  const description = message || descriptions[status] || t(keys.host.error.generic_description);

  return (
    <>
      <Head title="Error" />
      <ErrorScreen hero={status} title={title} description={description} accent={accents[status]}>
      <Button asChild className="gap-1.5">
        <Link href="/">
          <Home className="h-4 w-4" />
          {t(keys.host.error.go_home)}
        </Link>
      </Button>
      <Button variant="outline" onClick={() => window.history.back()} className="gap-1.5">
        <LifeBuoy className="h-4 w-4" />
        {t(keys.host.error.go_back)}
      </Button>
    </ErrorScreen>
    </>
  );
}

export default ErrorPage;
