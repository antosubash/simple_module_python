/**
 * Clipboard write that reports failure instead of throwing.
 *
 * The clipboard API is unavailable over plain http and in some embedded
 * webviews. Doctor's actions all end in "we put a command where you can paste
 * it", so a caller needs to know whether that actually happened — it can then
 * say so rather than claiming a copy that never occurred.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
