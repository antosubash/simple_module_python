import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionTitle } from './SectionTitle';

describe('SectionTitle', () => {
  test('renders heading text', () => {
    render(<SectionTitle>Users</SectionTitle>);
    expect(screen.getByText('Users')).toBeInTheDocument();
  });

  test('uses h3 by default', () => {
    render(<SectionTitle>Users</SectionTitle>);
    expect(screen.getByRole('heading', { level: 3 })).toBeInTheDocument();
  });

  test('honors as="h2" override', () => {
    render(<SectionTitle as="h2">Reports</SectionTitle>);
    expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument();
  });

  test('shows optional description', () => {
    render(<SectionTitle description="Lifetime totals across all tenants">Reports</SectionTitle>);
    expect(screen.getByText(/lifetime totals/i)).toBeInTheDocument();
  });

  test('places right-slot content', () => {
    render(<SectionTitle right={<button type="button">Add</button>}>Reports</SectionTitle>);
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument();
  });
});
