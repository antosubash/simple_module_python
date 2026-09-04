/** Shapes of the `FileStorage/Browse` Inertia props — mirrors endpoints/views.py. */

export interface StoredFile {
  id: string;
  filename: string;
  size_bytes: number;
  content_type: string;
  backend: string;
  uploaded_by: string | null;
  /** ``uploaded_by`` resolved server-side to a name; "—" when nobody was recorded. */
  uploaded_by_label: string;
  created_at: string | null;
}

export interface Pagination {
  page: number;
  perPage: number;
  total: number;
}

export interface ContentTypeFacet {
  value: string;
  count: number;
}

export interface UploaderFacet {
  id: string;
  label: string;
  count: number;
}

export interface FileFilters {
  q: string;
  content_type: string;
  uploaded_by: string;
}

export interface BrowseProps {
  files: StoredFile[];
  pagination: Pagination;
  filters: FileFilters;
  content_types: ContentTypeFacet[];
  uploaders: UploaderFacet[];
  backend: string;
  used_bytes: number;
  /** Null until an operator says what the bucket's ceiling is. */
  quota_bytes: number | null;
  max_file_size_bytes: number;
  /** Null means any type is accepted. */
  allowed_content_types: string[] | null;
}
