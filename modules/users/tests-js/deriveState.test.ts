/**
 * The TypeScript half of `users.admin.user_state.user_state`.
 *
 * `deriveState` exists because disabling an account from the edit page updates
 * local state without a reload, so the status pill has to be recomputed rather
 * than read off the prop it was rendered from. That makes it a second
 * implementation of a rule the server also applies, and nothing pinned the two
 * together — the first edit to either would have drifted them silently.
 *
 * These cases mirror `modules/users/tests/test_user_state.py::CASES` exactly.
 * Changing one without the other is the failure this pair is here to catch.
 */
import { describe, expect, test } from 'vitest';
import { deriveState } from '../users/admin/components/user-list-item';

const INVITED_AT = '2026-09-01T00:00:00Z';

const CASES: Array<[boolean, boolean, string | null, string]> = [
  [true, true, null, 'active'],
  [true, true, INVITED_AT, 'active'],
  [true, false, INVITED_AT, 'invited'],
  [true, false, null, 'unverified'],
  [false, true, null, 'disabled'],
  [false, false, INVITED_AT, 'disabled'],
];

describe('deriveState', () => {
  test.each(CASES)(
    'active=%s verified=%s invitedAt=%s -> %s',
    (isActive, isVerified, invitedAt, expected) => {
      expect(deriveState(isActive, isVerified, invitedAt)).toBe(expected);
    },
  );

  test('disabled wins over everything else', () => {
    expect(deriveState(false, true, INVITED_AT)).toBe('disabled');
  });

  test('an unverified account splits on whether somebody invited it', () => {
    expect(deriveState(true, false, INVITED_AT)).toBe('invited');
    expect(deriveState(true, false, null)).toBe('unverified');
  });
});
