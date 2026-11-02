import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Upload } from 'lucide-react';
import { useRef } from 'react';

interface Props {
  /** Hands the files to the page, which owns the queue and the toasts. */
  onFiles: (files: File[]) => void;
  busy: boolean;
}

/** The header's "Upload files" button. The dashed strip is `DropzoneStrip`. */
export function UploadDropzone({ onFiles, busy }: Props) {
  const { t } = useT();
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          const list = e.target.files;
          if (list && list.length > 0) onFiles(Array.from(list));
          // Re-selecting the same file must fire `change` again.
          e.target.value = '';
        }}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={busy} className="max-lg:min-h-11">
        <Upload />
        {busy ? t(keys.file_storage.browse.uploading) : t(keys.file_storage.browse.upload_button)}
      </Button>
    </>
  );
}
