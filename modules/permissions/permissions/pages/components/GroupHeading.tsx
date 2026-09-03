import { groupTag, type PermissionGroup } from './permission-groups';

/**
 * A module's name in the card header.
 *
 * The deck labels each card with the package slug, but the registry's own
 * label is what the rest of the admin calls the module — so the display name
 * leads, and the slug follows only when it says something the name does not
 * ("Files" is `file_storage`; "Background Tasks" is exactly what it looks
 * like).
 */
export function GroupHeading({ group }: { group: PermissionGroup }) {
  const tag = groupTag(group);
  return (
    <span className="flex min-w-0 flex-1 items-baseline gap-2">
      <code className="truncate font-mono text-sm font-semibold text-foreground">{group.name}</code>
      {tag && <code className="truncate font-mono text-[11px] text-muted-foreground">{tag}</code>}
    </span>
  );
}
