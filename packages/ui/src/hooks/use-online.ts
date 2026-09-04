import { useEffect, useState } from 'react';

/**
 * Track browser connectivity.
 *
 * `navigator.onLine` is only read once, at mount — after that the `online` /
 * `offline` events are the source of truth. Reading it on every render would
 * not re-render on its own, since it is not reactive state.
 *
 * Treated as optimistic: `onLine === false` reliably means "no network", but
 * `true` only means an interface is up, not that the server is reachable. So
 * this is used to explain a failure, never to gate a request.
 */
export function useOnline(): boolean {
  const [online, setOnline] = useState(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    // Re-sync on mount: the connection may have changed between the initial
    // state and the listeners being attached.
    setOnline(navigator.onLine);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  return online;
}
