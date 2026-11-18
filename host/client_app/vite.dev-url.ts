// smpy dev resolves dotenv once in Python and supplies the same URL to both children.
export function viteDevServer(): { origin: string; port: number } {
  // SM_VITE_PORT is deprecated (removal in 0.0.49): direct legacy npm launches still accept it.
  const raw =
    process.env.SM_VITE_DEV_URL || `http://localhost:${process.env.SM_VITE_PORT || '5050'}`;
  const url = new URL(raw);
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(`SM_VITE_DEV_URL must be a full HTTP(S) URL, got: ${raw}`);
  }
  return { origin: url.origin, port: url.port ? Number(url.port) : 5050 };
}
