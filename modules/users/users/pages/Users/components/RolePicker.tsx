import { keys, useT } from '@simple-module-py/i18n';

export interface Role {
  id: string;
  name: string;
}

interface Props {
  roles: Role[];
  selected: string[];
  onToggle: (roleName: string) => void;
  label?: string;
}

/** Multi-select role chips, shared by both modes of the add-people form. */
export function RolePicker({ roles, selected, onToggle, label }: Props) {
  const { t } = useT();
  if (roles.length === 0) return null;

  // Resolved here rather than in the signature: t() cannot be called at module
  // scope. An empty string means "the caller labelled this itself" — Details
  // puts "Roles" above the row with a link beside it — so nothing is rendered
  // rather than an empty span holding open a line of space.
  const resolvedLabel = label ?? t(keys.users.role_picker.default_label);

  return (
    <div className="space-y-2">
      {resolvedLabel && (
        <span className="block text-sm font-medium text-muted-foreground">{resolvedLabel}</span>
      )}
      <div className="flex flex-wrap gap-1.5">
        {roles.map((role) => {
          const active = selected.includes(role.name);
          return (
            <button
              key={role.id}
              type="button"
              aria-pressed={active}
              onClick={() => onToggle(role.name)}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors max-lg:min-h-11 ${
                active
                  ? 'border-primary-200 bg-primary-600/10 text-primary-700'
                  : 'border-border bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {role.name}
              {/* The deck marks the selected chip "admin ✓". `aria-pressed`
                  already says so to a screen reader; the tick says it to
                  everyone else, since tint alone is the only other cue. */}
              {active && <span aria-hidden="true"> ✓</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
