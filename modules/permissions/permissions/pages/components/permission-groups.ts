/**
 * Shapes and filtering shared by the two permission editors.
 *
 * Both screens render the same registry: modules grouped by display name,
 * each holding sorted permission keys. Only the filters differ, so the
 * narrowing lives here and each page passes the options it offers.
 */

export interface PermissionGroup {
  name: string;
  permissions: string[];
}

/** A module, narrowed to the rows the current filters keep. */
export interface FilteredGroup {
  /** The whole module — header counts and "select all" mean the module. */
  group: PermissionGroup;
  /** The keys still visible after filtering. Never empty. */
  permissions: string[];
}

/**
 * The key prefix every permission in a group shares — `file_storage` for the
 * group the registry calls "Files". Empty when the keys disagree.
 */
export function groupPrefix(group: PermissionGroup): string {
  const first = group.permissions[0];
  if (first === undefined) return '';
  const prefix = first.split('.')[0] ?? '';
  return group.permissions.every((key) => key.split('.')[0] === prefix) ? prefix : '';
}

/**
 * The slug to show beside the display name, or '' when it would only repeat
 * it. "Files" earns a `file_storage` tag; "Background tasks" does not.
 */
export function groupTag(group: PermissionGroup): string {
  const prefix = groupPrefix(group);
  const slug = group.name.trim().toLowerCase().replace(/\s+/g, '_');
  return prefix && prefix !== slug ? prefix : '';
}

interface FilterOptions {
  /**
   * Match the query against permission keys too, narrowing the rows inside a
   * module. The role editor's box says "modules or permissions"; the grants
   * editor's says "modules", and filters accordingly.
   */
  matchKeys?: boolean;
  /** Rows this rejects are dropped — how "Granted only" hides the rest. */
  keepKey?: (key: string) => boolean;
}

export function filterGroups(
  groups: PermissionGroup[],
  query: string,
  { matchKeys = false, keepKey }: FilterOptions = {},
): FilteredGroup[] {
  const needle = query.trim().toLowerCase();
  const result: FilteredGroup[] = [];
  for (const group of groups) {
    // A module the query names keeps all of its rows; otherwise only the keys
    // that match survive, so searching "invite" narrows rather than nothing.
    const moduleMatches =
      needle === '' ||
      group.name.toLowerCase().includes(needle) ||
      groupPrefix(group).includes(needle);
    if (!moduleMatches && !matchKeys) continue;
    const permissions = group.permissions.filter(
      (key) =>
        (moduleMatches || key.toLowerCase().includes(needle)) && (keepKey ? keepKey(key) : true),
    );
    if (permissions.length > 0) result.push({ group, permissions });
  }
  return result;
}

/**
 * Index at which the last row of a two-column grid starts, so every earlier
 * row gets a bottom border and the last one does not.
 */
export function lastRowStart(count: number): number {
  return Math.floor((count - 1) / 2) * 2;
}
