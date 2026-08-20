import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { loadEnv } from 'vite';

// SM_VITE_DEV_URL (process env, then the project .env) drives the dev
// server's port and origin, so Vite and the backend read the same value and
// can never drift apart. The documented default stays http://localhost:5050.

// The project .env sits at the project root (next to .env.example), which may
// be one or more levels above client_app — mirror the backend's resolution
// (SM_PROJECT_ROOT override, then a bounded walk-up stopping at a repo
// boundary) so both sides read the same file, whatever directory
// node_modules landed in.
// Shared scratch dirs like /tmp are world-writable: a `.env` sitting there
// could belong to another local user. Mirrors the backend's
// `_is_world_writable_dir` guard. The starting dir is exempt — running
// *from* such a directory keeps the pre-existing "load the cwd's .env"
// fallback behavior.
function isWorldWritableDir(dir: string): boolean {
  try {
    return (fs.statSync(dir).mode & 0o002) !== 0;
  } catch {
    return false;
  }
}

export function findEnvDir(start: string): string {
  const explicitRoot = process.env.SM_PROJECT_ROOT;
  if (explicitRoot) return explicitRoot;
  let dir = start;
  const home = os.homedir();
  for (let i = 0; i < 5; i++) {
    // Never treat $HOME (or anything above it) as the project — a stray
    // ~/.env must not steer the dev server (same rule as the backend).
    if (dir === home) break;
    if (dir !== start && isWorldWritableDir(dir)) break;
    if (fs.existsSync(path.join(dir, '.env')) || fs.existsSync(path.join(dir, '.env.example'))) {
      return dir;
    }
    // A `.git` marks a project root — never ascend past one, or a nested
    // checkout would read the outer project's .env (same rule as the
    // backend). The boundary directory IS the project root, so return it
    // directly rather than falling through to `start` — matching the
    // Python twin (`find_env_file`), which anchors at the boundary too.
    if (fs.existsSync(path.join(dir, '.git'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return start;
}

export function viteDevServer(startDir: string): { origin: string; port: number } {
  // loadEnv parses .env with the same dotenv semantics the backend uses
  // (quotes, inline comments, `export` prefixes), and a real process env var
  // wins over the file — the same precedence as pydantic-settings.
  const env = loadEnv(process.env.NODE_ENV ?? 'development', findEnvDir(startDir), 'SM_');
  const raw = env.SM_VITE_DEV_URL ?? 'http://localhost:5050';
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error(`SM_VITE_DEV_URL must be a full URL like http://localhost:5050, got: ${raw}`);
  }
  // A scheme-less value ("localhost:5310") parses as protocol "localhost:"
  // with origin "null" — catch it here rather than shipping a broken origin.
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error(`SM_VITE_DEV_URL must be a full URL like http://localhost:5050, got: ${raw}`);
  }
  return {
    // .origin normalizes away trailing slashes/paths that would otherwise
    // produce double-slash asset URLs in server.origin.
    origin: url.origin,
    // No explicit port means the URL is fronted by a proxy (https://dev.example.com):
    // keep binding the documented local default — binding 80/443 directly
    // needs privileges and would crash under strictPort.
    port: url.port ? Number(url.port) : 5050,
  };
}
