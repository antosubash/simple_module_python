// i18n-exempt-file: e2e fixture page, never shown to users
import { router } from '@inertiajs/react';
import { buttonClass, E2ePage, Value } from './components/E2ePage';

type Props = {
  stamp: number;
  a?: number;
  b?: number;
  nested?: { x?: number; y?: number };
};
export default function Partial({ stamp, a, b, nested }: Props) {
  return (
    <E2ePage title="Partial reloads">
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          className={buttonClass}
          data-testid="e2e-only-a"
          onClick={() => router.reload({ only: ['a'] })}
        >
          Reload only a
        </button>
        <button
          type="button"
          className={buttonClass}
          data-testid="e2e-except-b"
          onClick={() => router.reload({ except: ['b'] })}
        >
          Reload except b
        </button>
        <button
          type="button"
          className={buttonClass}
          data-testid="e2e-only-nested-x"
          onClick={() => router.reload({ only: ['nested.x'] })}
        >
          Reload only nested.x
        </button>
      </div>
      <Value name="stamp" value={stamp} />
      <Value name="a" value={a} />
      <Value name="b" value={b} />
      <Value name="nested-x" value={nested?.x} />
      <Value name="nested-y" value={nested?.y} />
    </E2ePage>
  );
}
