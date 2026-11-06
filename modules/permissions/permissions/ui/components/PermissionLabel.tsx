import { cleanLabel } from './permission-groups';

interface Props {
  permissionKey: string;
  /** Free text from a runtime permission source — rendered as plain text only. */
  label?: string;
  dimmed?: boolean;
  className?: string;
}

/**
 * A permission's identity. The key is always visible: a source-supplied label is
 * secondary text above it, never a replacement, so a label cannot make one
 * permission look like another.
 */
export function PermissionLabel({ permissionKey, label, dimmed = false, className = '' }: Props) {
  const text = cleanLabel(label);
  const tone = dimmed ? 'text-muted-foreground' : 'text-foreground';
  return (
    <span className={`flex min-w-0 flex-col ${className}`}>
      {text && <span className={`break-words text-[13px] ${tone}`}>{text}</span>}
      <code className={`break-all font-mono text-[12px] ${tone}`}>{permissionKey}</code>
    </span>
  );
}
