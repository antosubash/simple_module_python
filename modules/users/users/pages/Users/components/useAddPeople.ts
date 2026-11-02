import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { apiResult, NETWORK_FAILURE } from '@simple-module-py/ui/lib/api';
import type React from 'react';
import { useState } from 'react';
import { toast } from 'sonner';
import { api } from '../../api';
import { isPlausibleEmail } from '../invite-emails';
import type { InviteResult } from './InviteResults';

export type Mode = 'invite' | 'create';

const USERS_INDEX = '/admin/users/';

function initialMode(): Mode {
  if (typeof window === 'undefined') return 'invite';
  return new URLSearchParams(window.location.search).get('mode') === 'create' ? 'create' : 'invite';
}

/** State and submit flow for both modes of the Add people screen. */
export function useAddPeople() {
  const { t } = useT();

  const [mode, setMode] = useState<Mode>(initialMode);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<InviteResult[]>([]);
  const [retrying, setRetrying] = useState<string | null>(null);

  // Invite mode
  const [emails, setEmails] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  // Create mode
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');

  const toggleRole = (roleName: string) =>
    setSelectedRoles((prev) =>
      prev.includes(roleName) ? prev.filter((r) => r !== roleName) : [...prev, roleName],
    );

  // Invalid chips are excluded rather than blocking: one typo in a pasted
  // column must not hold up the other nineteen addresses.
  const validEmails = emails.filter(isPlausibleEmail);

  /** A failed result as the form's error line; the network case reads "try again". */
  const failWith = (res: { status: number; detail: string | null }, fallback: string) =>
    setError(
      res.status === NETWORK_FAILURE
        ? t(keys.users.common.error_try_again)
        : (res.detail ?? fallback),
    );

  async function postInvites(addresses: string[]): Promise<InviteResult[] | null> {
    const res = await apiResult(
      api.POST('/api/users/admin/invite/bulk', {
        body: { emails: addresses, role_names: selectedRoles, message: message.trim() || null },
      }),
    );
    if (!res.ok) {
      failWith(res, t(keys.users.add_people.error_invite_failed));
      return null;
    }
    return (res.data?.results as InviteResult[] | undefined) ?? [];
  }

  async function submitInvite() {
    const next = await postInvites(validEmails);
    if (next === null) return;
    setResults(next);
    const sent = next.filter((r) => r.status === 'sent').length;
    if (sent > 0) toast.success(t(keys.users.add_people.toast_invites_sent, { count: sent }));
    // Only clear the box when nothing needs following up — otherwise the
    // admin loses the list they still have to act on.
    if (next.every((r) => r.status !== 'failed')) {
      setEmails([]);
      setMessage('');
    }
  }

  /** Re-post one address, replacing just its row in the last batch. */
  async function retry(address: string) {
    setRetrying(address);
    setError(null);
    try {
      const next = await postInvites([address]);
      if (next === null || next.length === 0) return;
      setResults((prev) => prev.map((row) => (row.email === address ? next[0] : row)));
    } finally {
      setRetrying(null);
    }
  }

  async function submitCreate() {
    const res = await apiResult(
      api.POST('/api/users/admin', {
        body: { email, password, full_name: fullName || null, role_names: selectedRoles },
      }),
    );
    if (!res.ok) {
      failWith(res, t(keys.users.add_people.error_create_failed));
      return;
    }
    toast.success(t(keys.users.add_people.toast_user_created));
    router.visit(USERS_INDEX);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await (mode === 'invite' ? submitInvite() : submitCreate());
    } finally {
      setLoading(false);
    }
  }

  const canSubmit =
    mode === 'invite' ? validEmails.length > 0 : email.trim() !== '' && password !== '';

  const submitLabel = loading
    ? t(keys.users.add_people.submitting)
    : mode === 'invite'
      ? t(keys.users.add_people.submit_invite, { count: validEmails.length })
      : t(keys.users.add_people.submit_create);

  return {
    mode,
    changeMode: (next: Mode) => {
      setMode(next);
      setError(null);
    },
    selectedRoles,
    toggleRole,
    error,
    loading,
    results,
    retrying,
    retry,
    emails,
    setEmails,
    message,
    setMessage,
    email,
    setEmail,
    fullName,
    setFullName,
    password,
    setPassword,
    canSubmit,
    submitLabel,
    handleSubmit,
  };
}
