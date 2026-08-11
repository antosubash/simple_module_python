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
export function RolePicker({ roles, selected, onToggle, label = 'Roles' }: Props) {
  if (roles.length === 0) return null;

  return (
    <div className="space-y-2">
      <span className="block text-sm font-medium text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {roles.map((role) => {
          const active = selected.includes(role.name);
          return (
            <button
              key={role.id}
              type="button"
              aria-pressed={active}
              onClick={() => onToggle(role.name)}
              className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                active
                  ? 'border-primary-200 bg-primary-600/10 text-primary-700'
                  : 'border-border bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {role.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
