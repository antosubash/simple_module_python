// i18n-exempt-file: e2e fixture page, never shown to users
import { Link, router } from '@inertiajs/react';
import { buttonClass, E2ePage, Value } from './components/E2ePage';

export default function Redirects({ done }: { done: string }) {
  return (
    <E2ePage title="Redirects">
      <Value name="done" value={done} />
      <div className="flex flex-wrap gap-3">
        {(['put', 'patch', 'delete'] as const).map((method) => (
          <button
            type="button"
            key={method}
            className={buttonClass}
            data-testid={`e2e-redirect-${method}`}
            onClick={() => router[method]('/__e2e/inertia/redirects/mutate')}
          >
            {method.toUpperCase()} redirect
          </button>
        ))}
        <button
          type="button"
          className={buttonClass}
          data-testid="e2e-redirect-empty"
          onClick={() => router.post('/__e2e/inertia/redirects/empty')}
        >
          Empty response
        </button>
        <button
          type="button"
          className={buttonClass}
          data-testid="e2e-redirect-back"
          onClick={() => router.post('/__e2e/inertia/redirects/back')}
        >
          Redirect back
        </button>
        <Link href="/__e2e/inertia/redirects/fragment" data-testid="e2e-redirect-fragment">
          Go to section 2
        </Link>
        <Link href="/__e2e/inertia/redirects/external" data-testid="e2e-redirect-external">
          External location
        </Link>
      </div>
      <div style={{ height: '110vh' }} aria-hidden="true" />
      <h2 id="section-2" data-testid="e2e-section-2">
        Section 2
      </h2>
    </E2ePage>
  );
}
