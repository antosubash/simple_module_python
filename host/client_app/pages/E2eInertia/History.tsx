// i18n-exempt-file: e2e fixture page, never shown to users
import { Link, router } from '@inertiajs/react';
import { buttonClass, E2ePage, Value } from './components/E2ePage';

export default function History({ mode }: { mode: string }) {
  return (
    <E2ePage title="History and fragments">
      <Value name="history-mode" value={mode} />
      <nav className="flex gap-4">
        <Link href="/__e2e/inertia/history/encrypt" data-testid="e2e-history-encrypt">
          Encrypt history
        </Link>
        <Link href="/__e2e/inertia/history/clear" data-testid="e2e-history-clear">
          Clear history
        </Link>
        <Link
          href="/__e2e/inertia/history/fragment#history-section"
          data-testid="e2e-history-fragment"
        >
          Visit with fragment
        </Link>
        <button
          type="button"
          className={buttonClass}
          onClick={() => router.reload()}
          data-testid="e2e-history-preserve"
        >
          Reload preserving fragment
        </button>
      </nav>
      <div style={{ height: '110vh' }} aria-hidden="true" />
      <h2 id="history-section" data-testid="e2e-history-section">
        History section
      </h2>
    </E2ePage>
  );
}
