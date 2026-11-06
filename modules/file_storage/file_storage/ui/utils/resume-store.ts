/**
 * Remembers which server-side session belongs to which file, across reloads.
 *
 * A browser cannot keep a `File` handle through a reload, so resuming means
 * the user selects the same file again; this is how the page recognises it.
 * The key is name + size + lastModified — cheap, and wrong only for two
 * different files that agree on all three. Storage may be blocked or full
 * (private windows, quota), so every access is guarded and its absence just
 * means "no resume", never an error.
 */

const PREFIX = 'file_storage.upload.';

export function resumeKey(file: Pick<File, 'name' | 'size' | 'lastModified'>): string {
  return `${PREFIX}${file.name}:${file.size}:${file.lastModified}`;
}

export function loadSessionId(file: File): string | null {
  try {
    return window.localStorage.getItem(resumeKey(file));
  } catch {
    return null;
  }
}

export function saveSessionId(file: File, sessionId: string): void {
  try {
    window.localStorage.setItem(resumeKey(file), sessionId);
  } catch {
    // Without storage the upload still works; it just cannot be resumed.
  }
}

export function clearSessionId(file: File): void {
  try {
    window.localStorage.removeItem(resumeKey(file));
  } catch {
    // Nothing to clear.
  }
}
