import { keys, useT } from '@simple-module-py/i18n';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { X } from 'lucide-react';
import { type ChangeEvent, useRef } from 'react';

/**
 * Mirrors the server allow-list in `branding/images.py`. SVG is absent on
 * purpose — it is an XML document that can carry <script>, so the server
 * rejects it; offering it in the picker would only produce a 415.
 */
export const ACCEPTED_IMAGE_TYPES = 'image/png,image/jpeg,image/webp,image/gif,image/x-icon';

/** Matches the upload/clear route segments under `/api/branding/`. */
export type ImageKind = 'logo' | 'logo-dark' | 'favicon';

interface Slot {
  kind: ImageKind;
  /** Names the slot for screen readers and the thumbnail's alt text. */
  label: string;
  emptyLabel: string;
  url: string | null;
  /** The sidebar is near-black, so judge that variant against a dark surface. */
  dark?: boolean;
}

interface Props {
  logoUrl: string | null;
  logoDarkUrl: string | null;
  faviconUrl: string | null;
  onUpload: (kind: ImageKind, file: File) => void;
  onRemove: (kind: ImageKind) => void;
  disabled: boolean;
}

function Dropzone({
  slot,
  onUpload,
  onRemove,
  disabled,
  removeLabel,
}: {
  slot: Slot;
  onUpload: (kind: ImageKind, file: File) => void;
  onRemove: (kind: ImageKind) => void;
  disabled: boolean;
  removeLabel: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const surface = slot.dark ? 'bg-slate-900 text-slate-400' : 'text-muted-foreground';

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_IMAGE_TYPES}
        className="hidden"
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          const file = e.target.files?.[0];
          if (file) onUpload(slot.kind, file);
          e.target.value = '';
        }}
      />
      <button
        type="button"
        disabled={disabled}
        aria-label={slot.label}
        onClick={() => inputRef.current?.click()}
        className={`flex h-[62px] w-full items-center justify-center overflow-hidden rounded-[10px] border-[1.5px] border-dashed border-border p-1.5 text-[12.5px] transition-colors hover:border-primary disabled:opacity-50 ${surface}`}
      >
        {slot.url ? (
          <img src={slot.url} alt={slot.label} className="h-full w-full object-contain" />
        ) : (
          slot.emptyLabel
        )}
      </button>
      {slot.url && (
        <button
          type="button"
          disabled={disabled}
          aria-label={removeLabel}
          onClick={() => onRemove(slot.kind)}
          className="absolute -right-1.5 -top-1.5 inline-flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

/**
 * Logo, dark logo and favicon as one row of dashed drop targets.
 *
 * These upload the moment a file is picked, unlike everything else on the
 * form. Holding a File in the browser until Publish would mean a failed
 * Publish silently discards an image the user already watched land.
 */
export function ImageDropzones({
  logoUrl,
  logoDarkUrl,
  faviconUrl,
  onUpload,
  onRemove,
  disabled,
}: Props) {
  const { t } = useT();
  const upload = t(keys.branding.manage.dropzone_upload);
  const slots: Slot[] = [
    { kind: 'logo', label: t(keys.branding.manage.logo_label), emptyLabel: upload, url: logoUrl },
    {
      kind: 'logo-dark',
      label: t(keys.branding.manage.logo_dark_label),
      emptyLabel: upload,
      url: logoDarkUrl,
      dark: true,
    },
    {
      kind: 'favicon',
      label: t(keys.branding.manage.favicon_label),
      emptyLabel: t(keys.branding.manage.dropzone_favicon),
      url: faviconUrl,
    },
  ];

  return (
    <div className="flex flex-col gap-2">
      <Label className="text-[12.5px] font-medium text-muted-foreground">
        {t(keys.branding.manage.images_label)}
      </Label>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-[1fr_1fr_92px]">
        {slots.map((slot) => (
          <Dropzone
            key={slot.kind}
            slot={slot}
            onUpload={onUpload}
            onRemove={onRemove}
            disabled={disabled}
            removeLabel={t(keys.branding.manage.remove_button)}
          />
        ))}
      </div>
    </div>
  );
}
