import { groupTag, type PermissionGroup } from './permission-groups';

/**
 * A module's name in the card header.
 *
 * The deck labels each card with the package slug, but the registry's own
 * label is what the rest of the admin calls the module — so the display name
 * leads, and the slug follows only when it says something the name does not
 * ("Files" is `file_storage`; "Background tasks" is exactly what it looks
 * like). It stays a real heading: the cards are the page's structure, and a
 * screen reader navigating by heading is how you find one module among twelve.
 */
export function GroupHeading({ group }: { group: PermissionGroup }) {
  const tag = groupTag(group);
  return (
    <h3 className="flex min-w-0 flex-1 items-baseline gap-2 font-mono text-sm font-semibold text-foreground">
      <span className="truncate">{group.name}</span>
      {/* Whitespace-only text is not laid out in a flex container, but it does
          land in the accessible name — "Files file_storage", not "Filesfile_storage". */}
      {tag && ' '}
      {tag && <code className="truncate text-[11px] font-normal text-muted-foreground">{tag}</code>}
    </h3>
  );
}
