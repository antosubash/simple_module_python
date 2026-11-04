// i18n-exempt-file: e2e fixture page, never shown to users
import { Link, usePage } from '@inertiajs/react';
import { E2ePage } from './components/E2ePage';

export default function Index() {
  const { auth } = usePage<{ auth: { user: { email: string } | null } }>().props;
  const features = [
    'partial',
    'deferred',
    'merge',
    'once',
    'scroll',
    'forms',
    'redirects',
    'history',
    'visible',
  ] as const;
  return (
    <E2ePage title="Inertia feature lab">
      <p>
        Signed in: <span data-testid="e2e-user-email">{auth.user?.email}</span>
      </p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {features.map((slug) => (
          <li key={slug}>
            <Link
              href={`/__e2e/inertia/${slug}`}
              data-testid={`e2e-link-${slug}`}
              className="block rounded border p-4"
            >
              {slug}
            </Link>
          </li>
        ))}
      </ul>
    </E2ePage>
  );
}
