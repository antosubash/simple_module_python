import { render, screen } from '@testing-library/react';
import type React from 'react';
import { describe, expect, it } from 'vitest';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from './alert-dialog';

function open(action: React.ReactNode, cancel?: React.ReactNode) {
  render(
    <AlertDialog open>
      <AlertDialogContent>
        <AlertDialogTitle>Delete</AlertDialogTitle>
        <AlertDialogDescription>Sure?</AlertDialogDescription>
        {cancel}
        {action}
      </AlertDialogContent>
    </AlertDialog>,
  );
}

describe('AlertDialogAction', () => {
  it('lets a caller colour class win over the variant via tailwind-merge', () => {
    open(<AlertDialogAction className="bg-destructive">Go</AlertDialogAction>);
    const btn = screen.getByRole('button', { name: 'Go' });
    expect(btn.className).toContain('bg-destructive');
    expect(btn.className.split(/\s+/)).not.toContain('bg-primary');
    expect(btn.getAttribute('data-slot')).toBe('alert-dialog-action');
  });

  it('honours the variant prop', () => {
    open(<AlertDialogAction variant="destructive">Go</AlertDialogAction>);
    expect(screen.getByRole('button', { name: 'Go' }).className).toContain('bg-destructive');
  });
});

describe('AlertDialogCancel', () => {
  it('lets a caller class win over the outline variant', () => {
    open(<span />, <AlertDialogCancel className="bg-red-500">No</AlertDialogCancel>);
    const btn = screen.getByRole('button', { name: 'No' });
    expect(btn.className).toContain('bg-red-500');
    expect(btn.className).not.toContain('bg-background');
  });
});
