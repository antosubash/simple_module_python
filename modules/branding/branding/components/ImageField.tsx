import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { type ChangeEvent, useRef } from 'react';

/**
 * Mirrors the server allow-list in `branding/images.py`. SVG is absent on
 * purpose — it is an XML document that can carry <script>, so the server
 * rejects it; offering it in the picker would only produce a 415.
 */
export const ACCEPTED_IMAGE_TYPES = 'image/png,image/jpeg,image/webp,image/gif,image/x-icon';

interface ImageFieldProps {
  label: string;
  help: string;
  url: string | null;
  onUpload: (file: File) => void;
  onRemove: () => void;
  disabled: boolean;
  /** Preview swatch background — dark for logos meant for dark surfaces. */
  previewClassName?: string;
}

/** One upload/replace/remove slot with a thumbnail, for a single branding image. */
export function ImageField({
  label,
  help,
  url,
  onUpload,
  onRemove,
  disabled,
  previewClassName = 'bg-muted',
}: ImageFieldProps) {
  const { t } = useT();
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex items-center gap-4">
        <div
          className={`flex h-16 w-16 items-center justify-center overflow-hidden rounded-lg border ${previewClassName}`}
        >
          {url ? (
            <img src={url} alt={label} className="h-full w-full object-contain" />
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </div>
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_IMAGE_TYPES}
            className="hidden"
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = '';
            }}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => inputRef.current?.click()}
          >
            {url ? t(keys.branding.manage.replace_button) : t(keys.branding.manage.upload_button)}
          </Button>
          {url && (
            <Button type="button" variant="ghost" size="sm" disabled={disabled} onClick={onRemove}>
              {t(keys.branding.manage.remove_button)}
            </Button>
          )}
        </div>
      </div>
      <p className="text-xs text-muted-foreground">{help}</p>
    </div>
  );
}
