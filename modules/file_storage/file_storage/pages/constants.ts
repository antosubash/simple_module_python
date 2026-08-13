// TSX-side mirror of file_storage/constants.py — keep in sync.
// All routes, permission strings, and i18n keys used by Browse.tsx /
// UploadDropzone.tsx are declared here so the JSX has no magic strings.

export const ROUTES = {
  // Trailing slash matches the mounted route (and the sidebar entry). Without
  // it every filter keystroke and page click pays a 307 round trip through
  // Starlette's redirect_slashes before the real request.
  VIEW_BROWSE: '/file-storage/',
  API_UPLOAD: '/api/file-storage/upload',
  API_LIST: '/api/file-storage/files',
  apiFile: (id: string) => `/api/file-storage/files/${id}`,
  apiDownload: (id: string) => `/api/file-storage/files/${id}/download`,
} as const;

export const PERMISSIONS = {
  UPLOAD: 'file_storage.upload',
  DOWNLOAD: 'file_storage.download',
  DELETE: 'file_storage.delete',
  MANAGE: 'file_storage.manage',
} as const;

// Empty placeholder used when the row's uploader is missing (anonymous backfill).
export const UNKNOWN_UPLOADER = '—';
