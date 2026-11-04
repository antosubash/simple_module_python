// i18n-exempt-file: e2e fixture page, never shown to users
import { Head, Link, router } from '@inertiajs/react';
import { type ReactNode, useEffect, useState } from 'react';

export function E2ePage({ title, children }: { title: string; children: ReactNode }) {
  const [requests, setRequests] = useState(0);
  useEffect(() => router.on('finish', () => setRequests((value) => value + 1)), []);
  return (
    <>
      <Head title={title} />
      <nav className="mb-4 flex gap-4">
        <Link href="/__e2e/inertia/" data-testid="e2e-home">
          Inertia feature lab
        </Link>
        <span>
          Completed requests: <output data-testid="e2e-requests">{requests}</output>
        </span>
      </nav>
      <main className="space-y-4" data-testid="e2e-page">
        {children}
      </main>
    </>
  );
}

export function Value({ name, value }: { name: string; value: unknown }) {
  return (
    <pre data-testid={`e2e-value-${name}`} className="rounded border p-3">
      {value === undefined ? 'Not loaded' : JSON.stringify(value)}
    </pre>
  );
}

export const buttonClass = 'rounded border px-3 py-2 hover:bg-muted disabled:opacity-50';
