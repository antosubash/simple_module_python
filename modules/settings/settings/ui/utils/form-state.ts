import type { FieldMeta } from '../components/FieldInput';

/** Value inequality for form drafts: objects (JSON fields) compare by content. */
export function notEqual(a: unknown, b: unknown): boolean {
  if (a === b) return false;
  if (typeof a === 'object' || typeof b === 'object') {
    return JSON.stringify(a) !== JSON.stringify(b);
  }
  return true;
}

/**
 * Fields bucketed by their declared group, ungrouped first: those are the
 * module's main switches. Grouped only where the module said so; a "General"
 * heading over every field of a module with no groups carries no information.
 */
export function groupFields(fields: FieldMeta[]): [string, FieldMeta[]][] {
  const g = new Map<string, FieldMeta[]>();
  for (const f of fields) {
    const key = f.group ?? '';
    const bucket = g.get(key);
    if (bucket) bucket.push(f);
    else g.set(key, [f]);
  }
  return [...g.entries()].sort(([a], [b]) => Number(a !== '') - Number(b !== ''));
}
