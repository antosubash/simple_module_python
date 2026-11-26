import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';

type Props = {
  unsaved: number;
  busy: boolean;
  saved: boolean;
  onSave: () => void;
  onDiscard: () => void;
};

/**
 * Save and Discard, pinned to the bottom of the viewport.
 *
 * A long module (background tasks has 33 fields) used to need a scroll back
 * to a Save button in the header after editing the last field. On wide
 * screens the bar appears only while there is something to say; on phones it
 * stays, since that is where the thumb looks for the form's action.
 */
export function SaveBar({ unsaved, busy, saved, onSave, onDiscard }: Props) {
  const { t } = useT();
  const dirty = unsaved > 0;
  return (
    <div
      data-testid="settings-save-bar"
      className={`sticky bottom-0 z-10 -mx-4 mt-2 flex items-center gap-2 border-t border-border bg-card/95 px-4 py-3 shadow-[0_-4px_16px_rgba(20,30,40,0.06)] backdrop-blur supports-[backdrop-filter]:bg-card/80 sm:-mx-6 sm:px-6 lg:mx-0 lg:rounded-xl lg:border ${
        dirty || saved ? '' : 'lg:hidden'
      }`}
    >
      <div className="min-w-0 flex-1 text-sm">
        {dirty ? (
          <span className="flex items-center gap-2 font-medium">
            <span className="size-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
            {t(keys.settings.modules.unsaved_count, { count: unsaved })}
          </span>
        ) : saved ? (
          <p role="status" className="font-medium text-primary-text">
            {t(keys.settings.modules_form.saved_toast)}
          </p>
        ) : null}
      </div>
      {dirty && (
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={onDiscard}
          className="min-h-11"
        >
          {t(keys.settings.modules_form.discard)}
        </Button>
      )}
      <Button type="button" disabled={!dirty || busy} onClick={onSave} className="min-h-11">
        {busy ? t(keys.settings.modules_form.saving) : t(keys.settings.modules_form.save)}
      </Button>
    </div>
  );
}
