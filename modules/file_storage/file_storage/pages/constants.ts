// TSX-side mirror of file_storage/constants.py — keep in sync.
// All routes and permission strings used by Browse.tsx and its components are
// declared here so the JSX has no magic strings.

export const ROUTES = {
  // Trailing slash matches the mounted route (and the sidebar entry). Without
  // it every filter keystroke and page click pays a 307 round trip through
  // Starlette's redirect_slashes before the real request.
  VIEW_BROWSE: '/file-storage/',
  API_UPLOAD: '/api/file-storage/upload',
  API_LIST: '/api/file-storage/files',
  API_BULK_DELETE: '/api/file-storage/files/bulk-delete',
  apiFile: (id: string) => `/api/file-storage/files/${id}`,
  apiDownload: (id: string) => `/api/file-storage/files/${id}/download`,
} as const;

export const PERMISSIONS = {
  UPLOAD: 'file_storage.upload',
  DOWNLOAD: 'file_storage.download',
  DELETE: 'file_storage.delete',
  MANAGE: 'file_storage.manage',
} as const;

/**
 * Props an upload or a delete invalidates.
 *
 * A partial reload keeps the uploads card and the filter inputs mounted — the
 * whole point of that card is that it stays put — so every prop the table
 * header and body read has to be listed, or the usage total silently drifts
 * from the rows beneath it.
 */
export const RELOAD_PROPS: string[] = [
  'files',
  'pagination',
  'content_types',
  'uploaders',
  'used_bytes',
];
