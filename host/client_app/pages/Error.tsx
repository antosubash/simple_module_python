import { Head, Link } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { CopyableId } from '@simple-module-py/ui/components/CopyableId';
import { ErrorScreen } from '@simple-module-py/ui/components/ErrorScreen';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Home, LifeBuoy, LogIn } from 'lucide-react';

interface Props {
  status: number;
  message: string;
  correlation_id?: string;
  /** Provider-specific login URL, when an auth provider is installed. Only
   * used by the statuses where signing in is the actual remedy. */
  login_url?: string | null;
  /** A planned outage, not an incident — set by MaintenanceMiddleware. */
  maintenance?: boolean;
}

type Accent = 'primary' | 'warning' | 'destructive';

interface StatusCopy {
  title: string;
  description: string;
  accent: Accent;
}

/** One row per status, rather than three parallel Record<number, …> maps —
 * those drift the moment a status is added to one and missed in another. */
function useStatusCopy(status: number, maintenance: boolean): StatusCopy {
  const { t } = useT();
  const e = keys.host.error;

  if (maintenance) {
    // A planned outage. Same 503, but "we're doing this on purpose and it
    // will end" is a different message from "something is broken".
    return {
      title: t(e.maintenance_title),
      description: t(e.maintenance_description),
      accent: 'warning',
    };
  }

  const table: Record<number, StatusCopy> = {
    401: {
      title: t(e.unauthorized_title),
      description: t(e.unauthorized_description),
      accent: 'warning',
    },
    403: {
      title: t(e.forbidden_title),
      description: t(e.forbidden_description),
      accent: 'warning',
    },
    404: {
      title: t(e.not_found_title),
      description: t(e.not_found_description),
      accent: 'primary',
    },
    419: {
      title: t(e.session_expired_title),
      description: t(e.session_expired_description),
      accent: 'warning',
    },
    422: {
      title: t(e.invalid_request_title),
      description: t(e.invalid_request_description),
      accent: 'warning',
    },
    429: {
      title: t(e.rate_limited_title),
      description: t(e.rate_limited_description),
      accent: 'warning',
    },
    500: {
      title: t(e.server_error_title),
      description: t(e.server_error_description),
      accent: 'destructive',
    },
    503: {
      title: t(e.unavailable_title),
      description: t(e.unavailable_description),
      accent: 'destructive',
    },
  };

  return (
    table[status] ?? {
      title: t(e.generic_title),
      description: t(e.generic_description),
      accent: 'primary',
    }
  );
}

function ErrorPage({ status, message, correlation_id, login_url, maintenance }: Props) {
  const { t } = useT();
  const copy = useStatusCopy(status, Boolean(maintenance));

  // A server-supplied message wins over the canned description — it is the
  // specific reason, where the table only knows the status class.
  const description = message || copy.description;
  // The server already decided this: `login_url` is sent only for the
  // statuses in `_SIGN_IN_STATUSES` and is null otherwise. Re-deriving the
  // list here would mean editing it in two languages, where missing one
  // silently hides the button rather than failing.
  const showSignIn = Boolean(login_url);

  return (
    <>
      <Head title={copy.title} />
      <ErrorScreen
        hero={status}
        title={copy.title}
        description={description}
        accent={copy.accent}
        details={
          correlation_id ? (
            <div className="mt-5 flex flex-col items-center gap-1.5">
              <span className="text-xs text-muted-foreground">
                {t(keys.host.error.correlation_id_label)}
              </span>
              <CopyableId
                value={correlation_id}
                title={t(keys.host.error.correlation_id_copy)}
                className="px-2 py-1 text-[13px]"
              />
            </div>
          ) : undefined
        }
      >
        {showSignIn && (
          <Button asChild className="gap-1.5">
            <Link href={login_url as string}>
              <LogIn className="h-4 w-4" />
              {t(keys.host.error.sign_in)}
            </Link>
          </Button>
        )}
        <Button asChild variant={showSignIn ? 'outline' : 'default'} className="gap-1.5">
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
