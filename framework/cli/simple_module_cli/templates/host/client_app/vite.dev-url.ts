import fs from 'node:fs';
import path from 'node:path';

// SM_VITE_DEV_URL (process env, then the project .env) drives the dev
// server's port and origin, so Vite and the backend read the same value and
// can never drift apart. The documented default stays http://localhost:5050.
export function viteDevUrl(envDir: string): string {
  if (process.env.SM_VITE_DEV_URL) return process.env.SM_VITE_DEV_URL;
  let env = '';
  try {
    env = fs.readFileSync(path.join(envDir, '.env'), 'utf8');
  } catch {} // no .env yet (fresh checkout) — use the default
  const m = env.match(/^SM_VITE_DEV_URL\s*=\s*(\S+)\s*$/m);
  return m ? m[1].replace(/^['"]|['"]$/g, '') : 'http://localhost:5050';
}

export function viteDevPort(devUrl: string): number {
  return Number(new URL(devUrl).port || '5050');
}
