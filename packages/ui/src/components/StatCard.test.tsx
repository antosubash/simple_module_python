import { render, screen } from '@testing-library/react';
import { Activity } from 'lucide-react';
import { describe, expect, test } from 'vitest';

import { StatCard } from './StatCard';

describe('StatCard', () => {
  test('renders label and value', () => {
    render(<StatCard label="Total Users" value={42} icon={Activity} />);
    expect(screen.getByText('Total Users')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  test('shows optional delta badge', () => {
    render(<StatCard label="Errors" value="3" icon={Activity} delta="+1" deltaTone="warning" />);
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  test('omits delta when not provided', () => {
    render(<StatCard label="Active" value={1} icon={Activity} />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
