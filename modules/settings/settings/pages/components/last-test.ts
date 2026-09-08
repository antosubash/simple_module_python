/**
 * Last "Test connection" outcome, per package, for this browser tab.
 *
 * Nothing on the server records it: a health check is run on demand and its
 * result is not persisted anywhere. Rather than invent a store for it, the
 * outcome lives in `sessionStorage` — which is exactly the lifetime the fact
 * deserves. It answers "did I already try this?" for the admin who ran it,
 * and it correctly disappears for anyone else and for the next session.
 */

const PREFIX = 'sm.settings.last-test.';

export interface LastTest {
  ok: boolean;
  /** ISO timestamp, so `useRelativeTime` can render "4m ago". */
  at: string;
}

function storage(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.sessionStorage;
  } catch {
    // Blocked storage (private mode, third-party cookie policies). A missing
    // "last test" line is not worth breaking the settings form over.
    return null;
  }
}

export function readLastTest(pkg: string): LastTest | null {
  const raw = storage()?.getItem(PREFIX + pkg);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as LastTest;
    return typeof parsed?.at === 'string' ? { ok: !!parsed.ok, at: parsed.at } : null;
  } catch {
    return null;
  }
}

export function writeLastTest(pkg: string, ok: boolean): LastTest {
  const entry: LastTest = { ok, at: new Date().toISOString() };
  try {
    storage()?.setItem(PREFIX + pkg, JSON.stringify(entry));
  } catch {
    // Quota or blocked storage — the in-memory state still shows the result.
  }
  return entry;
}
