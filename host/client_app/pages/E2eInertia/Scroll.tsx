// i18n-exempt-file: e2e fixture page, never shown to users
import { InfiniteScroll, router } from '@inertiajs/react';
import { buttonClass, E2ePage } from './components/E2ePage';

type Props = { posts: { data: { id: number }[] }; filter: 'all' | 'even' };
export default function Scroll({ posts, filter }: Props) {
  return (
    <E2ePage title="Infinite scroll">
      <p data-testid="e2e-filter">{filter === 'all' ? 'All posts' : 'Even posts'}</p>
      <button
        type="button"
        className={buttonClass}
        data-testid="e2e-reset-filter"
        onClick={() =>
          router.reload({
            only: ['posts', 'filter'],
            reset: ['posts'],
            data: { page: 1, filter: filter === 'all' ? 'even' : 'all' },
          })
        }
      >
        Toggle filter and reset
      </button>
      <InfiniteScroll
        data="posts"
        onlyNext
        itemsElement="#e2e-posts"
        loading={<p data-testid="e2e-scroll-loading">Loading…</p>}
      >
        <ul id="e2e-posts" data-testid="e2e-posts" className="space-y-4">
          {posts.data.map((post) => (
            <li key={post.id} data-testid={`e2e-post-${post.id}`} className="rounded border p-10">
              Post {post.id}
            </li>
          ))}
        </ul>
      </InfiniteScroll>
    </E2ePage>
  );
}
