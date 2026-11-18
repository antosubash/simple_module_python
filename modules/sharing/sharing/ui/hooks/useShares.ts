import { keys, useT } from '@simple-module-py/i18n';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api, type components } from '../../pages/api.generated';

export type Share = components['schemas']['ShareOut'];
export type ShareCandidate = components['schemas']['ShareCandidate'];
export const MIN_QUERY = 3;
const SEARCH_DELAY_MS = 250;

/** Idle until open. Resource policies and tenant boundaries are enforced by the API. */
export function useShares(resourceType: string, resourceId: string, open = true) {
  const { t } = useT();
  const [shares, setShares] = useState<Share[]>([]);
  const [found, setFound] = useState<{ query: string; rows: ShareCandidate[] } | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const generation = useRef(0);
  const mutating = useRef(false);
  const term = query.trim();
  const tooShort = [...term].length < MIN_QUERY;

  useEffect(() => {
    const current = ++generation.current;
    setShares([]);
    setQuery('');
    setFound(null);
    setError(null);
    setPending(false);
    mutating.current = false;
    setLoading(open);
    if (open) {
      void apiResult(
        api.GET('/api/sharing/shares', {
          params: { query: { resource_type: resourceType, resource_id: resourceId } },
        }),
      ).then((result) => {
        if (generation.current !== current) return;
        if (result.ok) setShares(result.data);
        else setError(t(keys.sharing.dialog.failed));
        setLoading(false);
      });
    }
    return () => {
      generation.current++;
    };
  }, [resourceType, resourceId, open, t]);

  useEffect(() => {
    setSearchError(null);
    setSearching(open && !tooShort);
    if (!open || tooShort) return;
    let current = true;
    const timer = window.setTimeout(() => {
      void apiResult(
        api.GET('/api/sharing/candidates', {
          params: { query: { resource_type: resourceType, resource_id: resourceId, q: term } },
        }),
      ).then((result) => {
        if (!current) return;
        if (result.ok) setFound({ query: term, rows: result.data });
        else {
          setFound(null);
          setSearchError(t(keys.sharing.dialog.failed));
        }
        setSearching(false);
      });
    }, SEARCH_DELAY_MS);
    return () => {
      current = false;
      window.clearTimeout(timer);
    };
  }, [resourceType, resourceId, open, term, tooShort, t]);

  const grant = useCallback(
    async (candidate: ShareCandidate, role: string) => {
      if (!open || mutating.current) return;
      mutating.current = true;
      setPending(true);
      setError(null);
      const current = generation.current;
      const result = await apiResult(
        api.POST('/api/sharing/shares', {
          body: {
            resource_type: resourceType,
            resource_id: resourceId,
            subject_id: candidate.id,
            subject_type: 'user',
            role,
          },
        }),
      );
      if (generation.current !== current) return;
      if (result.ok)
        setShares((rows) => [...rows.filter((row) => row.id !== result.data.id), result.data]);
      else setError(t(keys.sharing.dialog.failed));
      mutating.current = false;
      setPending(false);
    },
    [resourceType, resourceId, open, t],
  );

  const revoke = useCallback(
    async (share: Share) => {
      if (!open || mutating.current) return;
      mutating.current = true;
      setPending(true);
      setError(null);
      const current = generation.current;
      const result = await apiResult(
        api.DELETE('/api/sharing/shares/{share_id}', {
          params: { path: { share_id: share.id } },
        }),
      );
      if (generation.current !== current) return;
      if (result.ok) setShares((rows) => rows.filter((row) => row.id !== share.id));
      else setError(t(keys.sharing.dialog.failed));
      mutating.current = false;
      setPending(false);
    },
    [open, t],
  );

  const held = new Set(shares.filter((share) => !share.expired).map((share) => share.subject_id));
  return {
    shares,
    query,
    setQuery,
    tooShort,
    loading,
    searching,
    pending,
    candidates:
      open && !tooShort && found?.query === term
        ? found.rows.filter((candidate) => !held.has(candidate.id))
        : [],
    error: searchError ?? error,
    grant,
    revoke,
  };
}
