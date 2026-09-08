import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';

interface Props {
  dirtyCount: number;
  saving: boolean;
  onDiscard: () => void;
  onSave: () => void;
}

/**
 * "3 unsaved changes · Discard · Save changes".
 *
 * The count, not just the fact: "Unsaved changes" is true whether you renamed
 * someone or rewrote their email and roles, and the number is what tells you
 * whether Discard is cheap.
 */
export function EditHeaderActions({ dirtyCount, saving, onDiscard, onSave }: Props) {
  const { t } = useT();
  const dirty = dirtyCount > 0;
  return (
    <div className="flex items-center gap-2">
      {dirty && (
        <span className="text-xs text-muted-foreground">
          {t(keys.users.edit.unsaved_changes, { count: dirtyCount })}
        </span>
      )}
      {/* Back to what is persisted, not to what the page loaded with —
          discarding must not visually undo a section that already saved. */}
      <Button
        variant="outline"
        onClick={onDiscard}
        disabled={!dirty || saving}
        className="max-lg:min-h-11"
      >
        {t(keys.users.common.discard)}
      </Button>
      <Button onClick={onSave} disabled={!dirty || saving} className="max-lg:min-h-11">
        {saving ? t(keys.users.common.saving) : t(keys.users.common.save_changes)}
      </Button>
    </div>
  );
}
