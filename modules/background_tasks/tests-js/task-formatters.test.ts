import { describe, expect, test } from 'vitest';
import {
  EM_DASH,
  formatCompactPayload,
  formatDuration,
  formatPayload,
  formatSoftware,
  formatTs,
  formatUptime,
  shortenId,
} from '../background_tasks/pages/constants';

describe('formatDuration', () => {
  test('is a dash until the run has finished', () => {
    // The deck's rule: a running row has no duration yet, only an elapsed
    // time, and the two must not sit in the same column.
    expect(formatDuration('2026-09-03T09:41:05Z', null)).toBe(EM_DASH);
  });

  test('is a dash for a row that never started', () => {
    expect(formatDuration(null, '2026-09-03T09:41:17Z')).toBe(EM_DASH);
  });

  test('reports seconds to one decimal', () => {
    expect(formatDuration('2026-09-03T09:41:05Z', '2026-09-03T09:41:17.400Z')).toBe('12.4s');
  });

  test('reports sub-second runs in milliseconds', () => {
    expect(formatDuration('2026-09-03T09:41:05.000Z', '2026-09-03T09:41:05.420Z')).toBe('420ms');
  });

  test('breaks a long run into minutes and seconds', () => {
    expect(formatDuration('2026-09-03T09:41:05Z', '2026-09-03T09:43:35Z')).toBe('2m 30s');
  });

  test('refuses to render a negative duration', () => {
    // Clock skew between the worker and the API, not a task that finished
    // before it started.
    expect(formatDuration('2026-09-03T09:41:17Z', '2026-09-03T09:41:05Z')).toBe(EM_DASH);
  });
});

describe('formatUptime', () => {
  test('drops to days and hours once a worker has been up that long', () => {
    expect(formatUptime(4 * 86_400 + 2 * 3600)).toBe('4d 2h');
  });

  test('reports hours and minutes below a day', () => {
    expect(formatUptime(5 * 3600 + 12 * 60)).toBe('5h 12m');
  });

  test('reports minutes below an hour', () => {
    expect(formatUptime(7 * 60 + 30)).toBe('7m');
  });

  test('reports seconds for a worker that just started', () => {
    expect(formatUptime(42)).toBe('42s');
  });

  test('has nothing to say about a worker that reported no uptime', () => {
    expect(formatUptime(null)).toBeNull();
  });

  test('rejects a nonsense reading rather than rendering it', () => {
    expect(formatUptime(Number.NaN)).toBeNull();
    expect(formatUptime(-1)).toBeNull();
  });
});

describe('formatSoftware', () => {
  test('turns the celery wire format into something readable', () => {
    expect(formatSoftware('py-celery:5.4.0')).toBe('celery 5.4.0');
  });

  test('keeps an identifier that carries no version', () => {
    expect(formatSoftware('py-celery')).toBe('celery');
  });

  test('leaves an unfamiliar identifier alone', () => {
    expect(formatSoftware('node-celery:1.2.3')).toBe('node-celery 1.2.3');
  });

  test('has nothing to say when the worker reported nothing', () => {
    expect(formatSoftware(null)).toBeNull();
  });
});

describe('formatPayload', () => {
  test('puts a list on one line with breathing room', () => {
    expect(formatPayload(['a91f2c'])).toBe('[ "a91f2c" ]');
  });

  test('puts a mapping on one line', () => {
    expect(formatPayload({ size: 512 })).toBe('{ "size": 512 }');
  });

  test('renders an empty payload as an empty literal, not as nothing', () => {
    expect(formatPayload([])).toBe('[]');
    expect(formatPayload({})).toBe('{}');
  });

  test('degrades rather than throwing on a cyclic payload', () => {
    const cyclic: Record<string, unknown> = {};
    cyclic.self = cyclic;
    expect(formatPayload(cyclic)).toBe('<unserialisable>');
  });
});

describe('shortenId', () => {
  test('keeps the ends of a uuid, which is what a reader matches on', () => {
    expect(shortenId('c1a47f2e-0b3d-4e5a-9c8b-1f0d7e558de2')).toBe('c1a4…8de2');
  });

  test('leaves a short id whole', () => {
    expect(shortenId('abc123')).toBe('abc123');
  });
});

describe('formatCompactPayload', () => {
  test('closes the brackets up but keeps the space after the colon', () => {
    // The deck's retry dialog: `{"size": 512}`. Without the space
    // `{"size":512}` reads as one token in a mono box inside a modal.
    expect(formatCompactPayload({ size: 512 })).toBe('{"size": 512}');
  });

  test('spaces the separators between entries', () => {
    expect(formatCompactPayload({ size: 512, mode: 'fit' })).toBe('{"size": 512, "mode": "fit"}');
    expect(formatCompactPayload(['a91f2c', 'b02d'])).toBe('["a91f2c", "b02d"]');
  });

  test('an empty payload stays empty', () => {
    expect(formatCompactPayload([])).toBe('[]');
    expect(formatCompactPayload({})).toBe('{}');
  });
});

describe('formatTs', () => {
  test('renders the deck format, not the reader\u2019s locale', () => {
    // A US machine gave "Sep 3, 08:48:40" — a different order and a comma
    // away from every other timestamp in the product.
    const stamp = new Date(2026, 8, 3, 8, 48, 40).toISOString();

    expect(formatTs(stamp)).toBe('3 Sep 08:48:40');
  });

  test('a missing timestamp is a dash, so the column still lines up', () => {
    expect(formatTs(null)).toBe(EM_DASH);
    expect(formatTs('not a time')).toBe(EM_DASH);
  });
});
