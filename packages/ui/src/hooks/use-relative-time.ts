import { useT } from '@simple-module-py/i18n';
import {
  ageOf,
  RELATIVE_AGE_KEYS,
  type RelativeAge,
  relativeAge,
  relativeUntil,
} from '../lib/relative-time';

/**
 * Translated "3h ago" / "in 2d" for an ISO timestamp.
 *
 * `relativeAge` and `relativeUntil` deliberately return a key and a count so
 * they stay pure; nearly every caller then wants the finished sentence. This
 * pairs them with the page's own `t` so a list of timestamps is one hook call
 * rather than a translation dance at every cell.
 *
 * `now` is sampled once per render, so every timestamp on a screen is measured
 * against the same instant — two rows a millisecond apart cannot disagree
 * about which side of a bucket boundary they fall on.
 */
export function useRelativeTime(): {
  ago: (iso: string | null | undefined) => string;
  until: (iso: string | null | undefined) => string;
} {
  const { t } = useT();
  const now = Date.now();

  const render = (rel: RelativeAge) =>
    rel.count === undefined ? t(rel.key) : t(rel.key, { count: rel.count });

  return {
    ago: (iso) => render(relativeAge(ageOf(iso, now))),
    until: (iso) => {
      if (!iso) return t(RELATIVE_AGE_KEYS.unknown);
      const parsed = new Date(iso).getTime();
      if (Number.isNaN(parsed)) return t(RELATIVE_AGE_KEYS.unknown);
      return render(relativeUntil(parsed - now));
    },
  };
}
