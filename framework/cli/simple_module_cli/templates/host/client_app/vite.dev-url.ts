import fs from 'node:fs';
import path from 'node:path';
import { loadEnv } from 'vite';

// SM_VITE_DEV_URL (process env, then the project .env) drives the dev
// server's port and origin, so Vite and the backend read the same value and
// can never drift apart. The documented default stays http://localhost:5050.

// The project .env sits at the project root (next to .env.example), which may
// be one or more levels above client_app — mirror the backend's walk-up so
// both sides read the same file, whatever directory node_modules landed in.
export function findEnvDir(start: string): string {
  let dir = start;
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(dir, '.env')) || fs.existsSync(path.join(dir, '.env.example'))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return start;
}

export function viteDevUrl(startDir: string): string {
  // loadEnv parses .env with the same dotenv semantics the backend uses
  // (quotes, inline comments, `export` prefixes), and a real process env var
  // wins over the file — the same precedence as pydantic-settings.
  const env = loadEnv(process.env.NODE_ENV ?? 'development', findEnvDir(startDir), 'SM_');
  const raw = env.SM_VITE_DEV_URL ?? 'http://localhost:5050';
  try {
    // .origin normalizes away trailing slashes/paths that would otherwise
    // produce double-slash asset URLs in server.origin.
    return new URL(raw).origin;
  } catch {
    throw new Error(`SM_VITE_DEV_URL must be a full URL like http://localhost:5050, got: ${raw}`);
  }
}

export function viteDevPort(devUrl: string): number {
  const url = new URL(devUrl);
  if (url.port) return Number(url.port);
  // No explicit port: bind the one the URL implies, so the backend (which
  // hands this URL to the browser) and Vite agree instead of silently
  // drifting to 5050.
  return url.protocol === 'https:' ? 443 : 80;
}
