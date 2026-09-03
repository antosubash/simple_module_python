import { keys, useT } from '@simple-module-py/i18n';
import { Input } from '@simple-module-py/ui/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@simple-module-py/ui/components/ui/select';
import { Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { ContentTypeFacet, FileFilters, UploaderFacet } from '../types';

interface Props {
  filters: FileFilters;
  facets: ContentTypeFacet[];
  uploaders: UploaderFacet[];
  onChange: (next: FileFilters) => void;
}

/** Sentinel for "no filter" — Radix Select forbids an empty item value. */
export const ANY = '__all__';

/** Group a bucketful of `image/png`, `image/jpeg`, … under one `image/` entry. */
function families(facets: ContentTypeFacet[]): ContentTypeFacet[] {
  const totals = new Map<string, number>();
  for (const facet of facets) {
    const family = `${facet.value.split('/')[0]}/`;
    totals.set(family, (totals.get(family) ?? 0) + facet.count);
  }
  // A family with a single member says nothing the exact type doesn't.
  return [...totals.entries()]
    .filter(([family]) => facets.filter((f) => f.value.startsWith(family)).length > 1)
    .map(([value, count]) => ({ value, count }));
}

export function FileFilterBar({ filters, facets, uploaders, onChange }: Props) {
  const { t } = useT();
  const { q: search, content_type: contentType, uploaded_by: uploadedBy } = filters;
  const [draft, setDraft] = useState(search);
  // The last query this box asked the server for. Adopting `search` blindly
  // loses keystrokes: typing "report" fires the debounce at "repo", and when
  // that reply lands mid-word it would push "repo" back into the input and
  // swallow the rest. Ignoring the echo of our own request leaves the draft
  // alone while still adopting navigations we did not initiate — Back/Forward,
  // or a link carrying ?q=.
  const requested = useRef(search);

  useEffect(() => {
    if (search === requested.current) return;
    requested.current = search;
    setDraft(search);
  }, [search]);

  // Debounced so each keystroke isn't a round trip. Every dependency is a
  // primitive on purpose: `filters` is a fresh object on each Inertia render,
  // so depending on it would restart the timer forever and the search would
  // never fire while anything else on the page was updating.
  useEffect(() => {
    if (draft === search) return;
    const timeout = setTimeout(() => {
      requested.current = draft;
      onChange({ q: draft, content_type: contentType, uploaded_by: uploadedBy });
    }, 300);
    return () => clearTimeout(timeout);
  }, [draft, search, contentType, uploadedBy, onChange]);

  // Carries the current draft, so record it as requested for the same reason
  // the debounce does.
  function pick(change: Partial<FileFilters>) {
    requested.current = draft;
    onChange({ q: draft, content_type: contentType, uploaded_by: uploadedBy, ...change });
  }

  const grouped = families(facets);
  // A trailing "/" is a whole family, which the list shows as "image/*".
  const isFamily = contentType.endsWith('/');
  const selected = [...facets, ...grouped].find((f) => f.value === contentType);

  return (
    <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="relative flex-1 sm:max-w-sm">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t(keys.file_storage.filters.search_placeholder)}
          aria-label={t(keys.file_storage.filters.search_placeholder)}
        />
      </div>

      <Select
        value={contentType || ANY}
        onValueChange={(value) => pick({ content_type: value === ANY ? '' : value })}
      >
        <SelectTrigger
          className="w-full sm:w-56"
          aria-label={t(keys.file_storage.filters.type_label)}
        >
          {/* The trigger names the filter as well as its value — "image/png"
              alone does not say which column it narrows. */}
          <SelectValue placeholder={t(keys.file_storage.filters.type_label)}>
            {contentType
              ? t(keys.file_storage.filters.type_selected, {
                  value: isFamily ? `${contentType}*` : contentType,
                  count: selected?.count ?? 0,
                })
              : t(keys.file_storage.filters.type_label)}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>{t(keys.file_storage.filters.type_all)}</SelectItem>
          {grouped.map((facet) => (
            <SelectItem key={facet.value} value={facet.value}>
              {facet.value}* ({facet.count})
            </SelectItem>
          ))}
          {facets.map((facet) => (
            <SelectItem key={facet.value} value={facet.value}>
              {facet.value} ({facet.count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={uploadedBy || ANY}
        onValueChange={(value) => pick({ uploaded_by: value === ANY ? '' : value })}
      >
        <SelectTrigger
          className="w-full sm:w-52"
          aria-label={t(keys.file_storage.filters.uploader_label)}
        >
          <SelectValue placeholder={t(keys.file_storage.filters.uploader_label)} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>{t(keys.file_storage.filters.uploader_all)}</SelectItem>
          {uploaders.map((uploader) => (
            <SelectItem key={uploader.id} value={uploader.id}>
              {uploader.label} ({uploader.count})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
