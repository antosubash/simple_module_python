// i18n-exempt-file: e2e fixture page, never shown to users
import { Link, usePoll, WhenVisible } from '@inertiajs/react';
import { buttonClass, E2ePage, Value } from './components/E2ePage';

export default function Visible({ tick, below }: { tick: number; below?: number }) {
  const poll = usePoll(1000, { only: ['tick'] });
  return (
    <E2ePage title="Visibility, prefetch and polling">
      <Value name="tick" value={tick} />
      <button
        type="button"
        className={buttonClass}
        data-testid="e2e-poll-toggle"
        onClick={() => (poll.polling ? poll.stop() : poll.start())}
      >
        {poll.polling ? 'Stop polling' : 'Start polling'}
      </button>
      <Link href="/__e2e/inertia/partial" prefetch data-testid="e2e-prefetch-partial">
        Prefetch partial reloads
      </Link>
      <div style={{ height: '200vh' }} aria-hidden="true" data-testid="e2e-visible-spacer" />
      <WhenVisible data="below" fallback={<p data-testid="e2e-below-loading">Loading…</p>}>
        <Value name="below" value={below} />
      </WhenVisible>
    </E2ePage>
  );
}
