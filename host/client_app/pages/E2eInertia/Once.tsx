// i18n-exempt-file: e2e fixture page, never shown to users
import { Link, router } from '@inertiajs/react';
import { buttonClass, E2ePage, Value } from './components/E2ePage';

export default function Once({ cached, expiring }: { cached: number; expiring: number }) {
  return (
    <E2ePage title="Once props">
      <Value name="cached" value={cached} />
      <Value name="expiring" value={expiring} />
      <Link href="/__e2e/inertia/" data-testid="e2e-once-away">
        Visit index and return
      </Link>
      <button
        type="button"
        className={buttonClass}
        data-testid="e2e-refresh-once"
        onClick={() => router.reload({ only: ['cached'] })}
      >
        Refresh once
      </button>
      <button
        type="button"
        className={buttonClass}
        data-testid="e2e-refresh-expiring"
        onClick={() => router.reload({ only: ['expiring'] })}
      >
        Refresh expiring value
      </button>
    </E2ePage>
  );
}
