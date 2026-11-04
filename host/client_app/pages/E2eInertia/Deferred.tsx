// i18n-exempt-file: e2e fixture page, never shown to users
import { Deferred as InertiaDeferred } from '@inertiajs/react';
import { E2ePage, Value } from './components/E2ePage';

export default function Deferred({ fast, slow }: { fast?: number; slow?: number }) {
  return (
    <E2ePage title="Deferred groups">
      <InertiaDeferred data="fast" fallback={<p data-testid="e2e-fast-loading">Loading…</p>}>
        <Value name="fast" value={fast} />
      </InertiaDeferred>
      <InertiaDeferred data="slow" fallback={<p data-testid="e2e-slow-loading">Loading…</p>}>
        <Value name="slow" value={slow} />
      </InertiaDeferred>
      <InertiaDeferred
        data="fragile"
        fallback={<p data-testid="e2e-fragile-loading">Loading…</p>}
        rescue={<p data-testid="e2e-fragile-failed">Loader failed safely</p>}
      >
        <p data-testid="e2e-fragile-ready">Loader ready</p>
      </InertiaDeferred>
    </E2ePage>
  );
}
