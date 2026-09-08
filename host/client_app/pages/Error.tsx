import { Head, Link, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { CopyableId } from '@simple-module-py/ui/components/CopyableId';
import { ErrorScreen } from '@simple-module-py/ui/components/ErrorScreen';
import { InterpolatedText } from '@simple-module-py/ui/components/InterpolatedText';
import { Button } from '@simple-module-py/ui/components/ui/button';
import type { SharedProps } from '@simple-module-py/ui/types';
import type { ReactNode } from 'react';

interface Props {
  status: number;
  message: string;
  correlation_id?: string;
  /** The permission a `RequiresPermission` guard demanded, when the 403 came
   * from one. Null for role-gated and hand-raised 403s, which have no single
   * permission to name. */
  required_permission?: string | null;
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

/** From here up the fault is the server's, not the request's, so the remedy
 * is "try it again" rather than "back out of it" — and the correlation id is
 * worth quoting, because there is something on our side to go and look at.
 * A maintenance 503 keeps its amber accent and gains both: a reload is exactly
 * how a visitor finds out the window has closed. */
const SERVER_ERROR_MIN = 500;

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

function ErrorPage({
  status,
  message,
  correlation_id,
  required_permission,
  login_url,
  maintenance,
}: Props) {
  const { t } = useT();
  const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const copy = useStatusCopy(status, Boolean(maintenance));

  // Three sources, most specific first. A named permission beats everything:
  // it is the only wording that tells the reader what to go and ask for, and
  // the server's own message for that case is the guard's log sentence
  // ("Permission required: settings.manage"), not copy for a human. Otherwise
  // a server-supplied message wins over the canned description — it is the
  // specific reason, where the table only knows the status class.
  let description: ReactNode = message || copy.description;
  if (required_permission) {
    description = (
      <InterpolatedText
        render={(slot) => t(keys.host.error.forbidden_permission, { permission: slot })}
      >
        <code className="rounded bg-secondary px-1 py-0.5 font-mono text-[12.5px] text-foreground">
          {required_permission}
        </code>
      </InterpolatedText>
    );
  }

  // The server already decided this: `login_url` is sent only for the
  // statuses in `_SIGN_IN_STATUSES` and is null otherwise. Re-deriving the
  // list here would mean editing it in two languages, where missing one
  // silently hides the button rather than failing.
  const showSignIn = Boolean(login_url);
  // "Home" is wherever this visitor's app starts. Sending a signed-in user to
  // the marketing page makes them navigate back in through the nav.
  const homeHref = auth?.isAuthenticated ? '/dashboard/' : '/';

  return (
    <>
      {/* main's per-status title is already translated and more specific than
          a single generic one, so it wins over host.error.head_title. */}
      <Head title={copy.title} />
      <ErrorScreen
        hero={status}
        title={copy.title}
        description={description}
        accent={copy.accent}
        details={
          // Only where it is actionable. The id is the handle on a server
          // failure worth reporting; on a 403 or a 404 it is a hex string
          // asking to be mistaken for the problem.
          status >= SERVER_ERROR_MIN && correlation_id ? (
            <CopyableId
              value={correlation_id}
              // The chip is short enough to read; the clipboard keeps the full
              // id, so what lands in a support ticket still matches the logs.
              // i18n-exempt: `req_` is an id prefix, not prose.
              label={`req_${correlation_id.slice(0, 8)}`}
              title={t(keys.host.error.correlation_id_copy)}
              // Size only. `CopyableId` concatenates rather than merging
              // classes, so overriding its colour utilities would leave the
              // winner to CSS source order rather than this call.
              className="rounded-lg px-3 py-2 text-[12.5px]"
            />
          ) : undefined
        }
      >
        {showSignIn && (
          <Button asChild className="max-lg:min-h-11">
            <Link href={login_url as string}>{t(keys.host.error.sign_in)}</Link>
          </Button>
        )}
        <Button asChild variant={showSignIn ? 'outline' : 'default'} className="max-lg:min-h-11">
          <Link href={homeHref}>{t(keys.host.error.go_home)}</Link>
        </Button>
        {status >= SERVER_ERROR_MIN ? (
          // Inertia reload, not location.reload(): it re-issues the same visit
          // and swaps the page in place, so a transient 500 resolves without
          // throwing away the history entry.
          <Button variant="outline" onClick={() => router.reload()} className="max-lg:min-h-11">
            {t(keys.host.error.retry)}
          </Button>
        ) : (
          <Button
            variant="outline"
            onClick={() => window.history.back()}
            className="max-lg:min-h-11"
          >
            {t(keys.host.error.go_back)}
          </Button>
        )}
      </ErrorScreen>
    </>
  );
}

export default ErrorPage;
