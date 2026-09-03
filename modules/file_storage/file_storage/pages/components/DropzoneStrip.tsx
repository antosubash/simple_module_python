import { keys, useT } from '@simple-module-py/i18n';
import { cn } from '@simple-module-py/ui/lib/utils';
import { useRef, useState } from 'react';

interface Props {
  onFiles: (files: File[]) => void;
  /** Rendered after the separator: "pdf, png, csv, sql" or "any type". */
  types: string;
  /** Largest single upload the server will take, already formatted. */
  maxSize: string;
  disabled: boolean;
}

/**
 * The dashed strip files can be dragged onto.
 *
 * The header button alone made drag-and-drop invisible — the browser's default
 * response to a dropped file is to navigate away from the page, which reads as
 * the app throwing the file away. This claims the drop and says what will be
 * accepted before anyone spends a minute uploading something that won't be.
 */
export function DropzoneStrip({ onFiles, types, maxSize, disabled }: Props) {
  const { t } = useT();
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function handle(list: FileList | null) {
    setOver(false);
    if (disabled || !list || list.length === 0) return;
    onFiles(Array.from(list));
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          handle(e.target.files);
          // Re-selecting the same file must fire `change` again.
          e.target.value = '';
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          handle(e.dataTransfer.files);
        }}
        className={cn(
          'mb-4 flex w-full flex-wrap items-center justify-center gap-x-3 gap-y-1',
          'rounded-xl border-[1.5px] border-dashed border-primary bg-primary-600/10',
          'px-4 py-5 text-center transition-colors',
          'disabled:pointer-events-none disabled:opacity-60',
          over && 'bg-primary-600/20',
        )}
      >
        <span className="text-sm font-medium text-primary-700">
          {t(keys.file_storage.upload.drop_here)}
        </span>
        <span className="text-[13px] text-muted-foreground">
          {t(keys.file_storage.upload.browse_hint, { types, size: maxSize })}
        </span>
      </button>
    </>
  );
}
