import { router } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { Button } from '@simple-module/ui/components/ui/button';
import { Upload } from 'lucide-react';
import { useRef, useState } from 'react';
import { toast } from 'sonner';

import { ROUTES } from '../constants';

export function UploadDropzone() {
  const { t } = useT();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        const resp = await fetch(ROUTES.API_UPLOAD, {
          method: 'POST',
          body: form,
        });
        if (!resp.ok) {
          toast.error(t(keys.file_storage.toasts.upload_failed));
        } else {
          toast.success(t(keys.file_storage.toasts.uploaded, { name: file.name }));
        }
      }
      router.reload({ only: ['files', 'pagination'] });
    } finally {
      setBusy(false);
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
