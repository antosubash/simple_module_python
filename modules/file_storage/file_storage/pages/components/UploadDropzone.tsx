import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Upload } from 'lucide-react';
import { useRef } from 'react';
import { toast } from 'sonner';

interface Props {
  /** Hands the files to the page's upload queue, which reports progress. */
  onFiles: (files: FileList) => Promise<{ uploaded: number; failed: string[] }>;
  busy: boolean;
}

export function UploadDropzone({ onFiles, busy }: Props) {
  const { t } = useT();
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    try {
      const { uploaded, failed } = await onFiles(files);
      if (uploaded > 0) {
        toast.success(t(keys.file_storage.toasts.uploaded_count, { count: uploaded }));
      }
      // Failures also leave a row on screen; the toast is for the case where
      // the user has already scrolled away from the table.
      for (const name of failed) {
        toast.error(t(keys.file_storage.toasts.upload_failed_named, { name }));
      }
    } finally {
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      <Button onClick={() => inputRef.current?.click()} disabled={busy}>
        <Upload />
        {busy ? t(keys.file_storage.browse.uploading) : t(keys.file_storage.browse.upload_button)}
      </Button>
    </>
  );
}
