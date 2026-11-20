// smpy dev resolves dotenv once in Python and supplies the same URL to both children.
export function viteDevServer(): { origin: string; port: number } {
  const raw = process.env.SM_VITE_DEV_URL || 'http://localhost:5050';
  const url = new URL(raw);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(`SM_VITE_DEV_URL must be a full HTTP(S) URL, got: ${raw}`);
  }
  return { origin: url.origin, port: url.port ? Number(url.port) : 5050 };
}
