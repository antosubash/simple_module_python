import { render, screen } from '@testing-library/react';
import { Activity } from 'lucide-react';
import { describe, expect, test } from 'vitest';

import { StatCard } from './StatCard';

describe('StatCard', () => {
  test('renders label and value', () => {
    render(<StatCard label="Total users" value={42} icon={Activity} />);
    expect(screen.getByText('Total users')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  test('leaves the label in the sentence case it was given', () => {
    render(<StatCard label="Checks passing" value={9} />);
    // Not just the text: an `uppercase` class would render "CHECKS PASSING"
    // while `getByText` still matched, so the styling is the assertion.
    expect(screen.getByText('Checks passing')).not.toHaveClass('uppercase');
  });

  test('keeps the icon tile off phones', () => {
    // The deck's 390px frame is label + figure only; below `sm` the tile is
    // display:none rather than absent, so the desktop layout is unchanged.
    const { container } = render(<StatCard label="Files" value={3} icon={Activity} />);
    const tile = container.querySelector('svg')?.parentElement;
    expect(tile).toHaveClass('hidden');
    expect(tile).toHaveClass('sm:inline-flex');
  });

  test('sets the value at the deck size', () => {
    render(<StatCard label="Members" value={7} />);
    expect(screen.getByText('7')).toHaveClass('text-[30px]');
  });

  test('renders without an icon', () => {
    const { container } = render(<StatCard label="Members" value={7} />);
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeNull();
  });

  test('shows the delta as text coloured by its tone', () => {
    render(<StatCard label="Errors" value="3" icon={Activity} delta="+1" deltaTone="warning" />);
    expect(screen.getByText('+1')).toHaveClass('text-amber-700');
  });

  test('omits the delta when not provided', () => {
    const { container } = render(<StatCard label="Active" value={1} icon={Activity} />);
    expect(container.querySelector('[data-slot="stat-delta"]')).toBeNull();
  });

  test('renders a muted suffix after the value', () => {
    render(<StatCard label="Seats" value={5} suffix="/ 8" />);
    expect(screen.getByText('/ 8')).toBeInTheDocument();
  });

  test('tints the whole card for a warning tone', () => {
    const { container } = render(<StatCard label="Queue" value={12} tone="warning" />);
    const card = container.querySelector('[data-slot="card"]');
    expect(card).toHaveClass('border-amber-200');
    // The label is tinted with the figure, not left neutral on the tint.
    expect(card).toHaveClass('[&_[data-slot=stat-label]]:text-amber-700');
  });

  test('tints the whole card for a destructive tone', () => {
    const { container } = render(<StatCard label="Failed" value={3} tone="destructive" />);
    const card = container.querySelector('[data-slot="card"]');
    expect(card).toHaveClass('border-red-200');
    expect(card).toHaveClass('[&_[data-slot=stat-label]]:text-red-700');
  });

  test('uses the compact deck padding instead of the shadcn card default', () => {
    const { container } = render(<StatCard label="Members" value={7} />);
    const card = container.querySelector('[data-slot="card"]');
    expect(card).toHaveClass('py-[18px]');
    expect(card).toHaveClass('gap-0');
    expect(card).not.toHaveClass('py-6');
  });

  test('accepts an extra class on the value', () => {
    render(<StatCard label="Uptime" value="99.9%" valueClassName="text-primary-700" />);
    expect(screen.getByText('99.9%')).toHaveClass('text-primary-700');
  });
});
