import { TableCell, TableRow } from '@simple-module-py/ui/components/ui/table';
import type React from 'react';

interface TableEmptyRowProps {
  /** How many columns the surrounding table has — sets the cell's colSpan. */
  columnCount: number;
  /** Usually an `<EmptyState />`, with whatever copy/action fits this table. */
  children: React.ReactNode;
}

/**
 * The row/cell shell around a table's "nothing here" state.
 *
 * Every admin list (users, tasks, files) wrapped `EmptyState` in the same
 * `TableRow`/`TableCell` scaffolding by hand — same `hover:bg-transparent`,
 * same `h-40` cell. That shell carries no per-table meaning, so it lives here
 * once; only the `EmptyState` passed as children differs per table.
 */
export function TableEmptyRow({ columnCount, children }: TableEmptyRowProps) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={columnCount} className="h-40">
        {children}
      </TableCell>
    </TableRow>
  );
}
