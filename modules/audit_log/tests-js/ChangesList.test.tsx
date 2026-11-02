import '@testing-library/jest-dom/vitest';
import { configureI18n } from '@simple-module-py/i18n';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

configureI18n({
  locale: 'en',
  messages: {
    'audit_log.changes.no_changes': 'no changes recorded',
    'audit_log.changes.fields_set_one': '{count} field set',
    'audit_log.changes.fields_set_other': '{count} fields set',
    'audit_log.changes.show_more': '+{count} more fields',
    'audit_log.changes.show_less': 'Show less',
  },
});

import { type Change, ChangesList } from '../audit_log/pages/components/ChangesList';

const FOUR: Change[] = [
  { field: 'value', old: '', new: 'mail.example.com' },
  { field: 'source', old: 'env', new: 'db' },
  { field: 'is_active', old: true, new: false },
  { field: 'disabled_at', old: null, new: '2026-08-19' },
];

describe('ChangesList', () => {
  test('a delete says nothing was recorded rather than showing a dash', () => {
    render(<ChangesList action="deleted" changes={[]} />);

    expect(screen.getByText('no changes recorded')).toBeInTheDocument();
  });

  test('an archive reads the same as a delete', () => {
    render(<ChangesList action="soft_deleted" changes={[]} />);

    expect(screen.getByText('no changes recorded')).toBeInTheDocument();
  });

  test('a create counts the fields instead of listing them', () => {
    render(<ChangesList action="created" changes={FOUR} />);

    expect(screen.getByText('4 fields set')).toBeInTheDocument();
  });

  test('an update spaces the arrow between the two values', () => {
    render(<ChangesList action="updated" changes={[FOUR[2]]} />);

    expect(screen.getByText(/^true → false$/)).toBeInTheDocument();
  });

  test('null and the empty string stay visibly different', () => {
    render(<ChangesList action="updated" changes={[FOUR[3], FOUR[0]]} />);

    // A field cleared to "" and a field nulled are different events; both
    // used to render as nothing at all.
    expect(screen.getByText(/^null → "2026-08-19"$/)).toBeInTheDocument();
    expect(screen.getByText(/^"" → "mail.example.com"$/)).toBeInTheDocument();
  });

  test('a missing old value reads as null, not as the empty string', () => {
    render(<ChangesList action="updated" changes={[{ field: 'source', new: 'db' }]} />);

    expect(screen.getByText(/^null → "db"$/)).toBeInTheDocument();
  });

  test('only the first two fields show, the rest behind a count', () => {
    render(<ChangesList action="updated" changes={FOUR} />);

    expect(screen.getByText('value')).toBeInTheDocument();
    expect(screen.getByText('source')).toBeInTheDocument();
    expect(screen.queryByText('is_active')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+2 more fields' })).toBeInTheDocument();
  });

  test('expanding reveals the rest and offers to collapse again', () => {
    render(<ChangesList action="updated" changes={FOUR} />);

    fireEvent.click(screen.getByRole('button', { name: '+2 more fields' }));

    expect(screen.getByText('is_active')).toBeInTheDocument();
    expect(screen.getByText('disabled_at')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument();
  });

  test('exactly two fields need no show-more control', () => {
    render(<ChangesList action="updated" changes={FOUR.slice(0, 2)} />);

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
