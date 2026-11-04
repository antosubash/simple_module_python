// i18n-exempt-file: e2e fixture page, never shown to users
import { router } from '@inertiajs/react';
import { useState } from 'react';
import { buttonClass, E2ePage, Value } from './components/E2ePage';

type Props = {
  page: number;
  items: number[];
  prepended: number[];
  tree: Record<string, unknown>;
  matched: { id: number; revision: number }[];
};
export default function Merge({ page: initialPage, ...props }: Props) {
  const [loading, setLoading] = useState(false);
  const [pages, setPages] = useState({
    items: initialPage,
    prepended: initialPage,
    tree: initialPage,
    matched: initialPage,
  });
  function more(name: keyof typeof props) {
    const page = pages[name] + 1;
    router.reload({
      onStart: () => setLoading(true),
      onFinish: () => setLoading(false),
      only: [name],
      data: { page },
      onSuccess: () => setPages((previous) => ({ ...previous, [name]: page })),
    });
  }
  return (
    <E2ePage title="Merging props">
      {(['items', 'prepended', 'tree', 'matched'] as const).map((name) => (
        <section key={name}>
          <h2>{name}</h2>
          <Value name={name} value={props[name]} />
          <button
            type="button"
            disabled={loading}
            className={buttonClass}
            data-testid={`e2e-more-${name}`}
            onClick={() => more(name)}
          >
            Load more
          </button>
        </section>
      ))}
      <button
        type="button"
        disabled={loading}
        className={buttonClass}
        data-testid="e2e-reset-items"
        onClick={() =>
          router.reload({
            onStart: () => setLoading(true),
            onFinish: () => setLoading(false),
            only: ['items'],
            data: { page: 1 },
            reset: ['items'],
            onSuccess: () => setPages((previous) => ({ ...previous, items: 1 })),
          })
        }
      >
        Reset items
      </button>
    </E2ePage>
  );
}
