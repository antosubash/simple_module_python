import { keys, useT } from '@simple-module-py/i18n';
import type React from 'react';
import { useEffect, useState } from 'react';
import { useOnline } from '../hooks/use-online';

/**
 * Connectivity bar shown while the browser reports no network.
 *
 * Mounted once at the app root rather than per-layout, so it also covers the
 * error and auth screens — losing the connection on the login page is exactly
 * when an unexplained failure is most confusing.
 *
 * Briefly confirms recovery instead of vanishing silently: a bar that just
 * disappears leaves the user unsure whether to retry what they were doing.
 */
const RESTORED_VISIBLE_MS = 3000;

export function OfflineBanner(): React.ReactElement | null {
  const { t } = useT();
  const online = useOnline();
  const [showRestored, setShowRestored] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    if (!online) {
      setWasOffline(true);
      setShowRestored(false);
      return;
    }
    if (!wasOffline) return;
    setShowRestored(true);
    const timer = window.setTimeout(() => {
      setShowRestored(false);
      setWasOffline(false);
    }, RESTORED_VISIBLE_MS);
    return () => window.clearTimeout(timer);
  }, [online, wasOffline]);

  if (online && !showRestored) return null;

  return (
    <div
      // `alert` while offline — it changes what the user can do right now, so
      // it should interrupt. `status` on recovery, which is just reassurance.
      role={online ? 'status' : 'alert'}
      className={`w-full px-4 py-2 text-center text-sm font-medium ${
        online ? 'bg-emerald-600 text-white' : 'bg-slate-800 text-white'
      }`}
    >
      {online ? (
        t(keys.host.offline.restored)
      ) : (
        <>
          <span className="font-semibold">{t(keys.host.offline.title)}</span>
          <span className="ml-2 opacity-90">{t(keys.host.offline.description)}</span>
        </>
      )}
    </div>
  );
}
