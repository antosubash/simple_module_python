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
import { useEffect, useState } from 'react';

export interface ContentTypeFacet {
  value: string;
  count: number;
}

interface Props {
  search: string;
  contentType: string;
  facets: ContentTypeFacet[];
  onChange: (next: { q: string; content_type: string }) => void;
}

/** Sentinel for "no type filter" — Radix Select forbids an empty item value. */
export const TYPE_ALL = '__all__';

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

export function FileFilterBar({ search, contentType, facets, onChange }: Props) {
  const { t } = useT();
  const [draft, setDraft] = useState(search);

  // Debounced so each keystroke isn't a round trip; the server value winning
  // on change keeps Back/Forward navigation in sync with the box.
  useEffect(() => setDraft(search), [search]);
  useEffect(() => {
    if (draft === search) return;
    const timeout = setTimeout(() => onChange({ q: draft, content_type: contentType }), 300);
    return () => clearTimeout(timeout);
  }, [draft, search, contentType, onChange]);

  const grouped = families(facets);

  return (
    <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="relative max-w-sm flex-1">
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
        value={contentType || TYPE_ALL}
        onValueChange={(value) =>
          onChange({ q: draft, content_type: value === TYPE_ALL ? '' : value })
        }
      >
        <SelectTrigger className="w-full sm:w-64">
          <SelectValue placeholder={t(keys.file_storage.filters.type_label)} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TYPE_ALL}>{t(keys.file_storage.filters.type_all)}</SelectItem>
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
    </div>
  );
}
