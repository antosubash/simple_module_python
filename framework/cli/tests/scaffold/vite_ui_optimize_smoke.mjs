// Runs Vite's dev dependency optimiser on @simple-module-py/ui in the cwd app and
// prints {optimized, errors} as JSON; exit 1 on any optimiser error (GH #1245).
import { createServer } from 'vite';
const errors = [];
const report = (code) => {
  const optimized = Object.keys(server?.environments.client.depsOptimizer?.metadata?.optimized ?? {});
  console.log(JSON.stringify({ optimized, errors: errors.map((e) => e.slice(0, 500)) }));
  process.exit(code ?? (errors.length || !optimized.includes('@simple-module-py/ui') ? 1 : 0));
};
setTimeout(() => { errors.push('timed out waiting for dependency optimisation'); report(1); }, 30_000).unref();
const record = (e) => errors.push(String(e?.message ?? e));
process.on('uncaughtException', record);
process.on('unhandledRejection', record);
const noop = () => {};
const server = await createServer({
  configFile: false, root: process.cwd(), logLevel: 'error',
  customLogger: { info: noop, warn: noop, warnOnce: noop, clearScreen: noop, hasWarned: false,
    hasErrorLogged: () => errors.length > 0, error: (msg) => errors.push(String(msg)) },
  server: { port: 0, host: '127.0.0.1' },
  optimizeDeps: { force: true, noDiscovery: true, include: ['@simple-module-py/ui'] },
});
await server.listen();
const optimizer = server.environments.client.depsOptimizer;
for (let i = 0; i < 150 && !errors.length; i++) {
  if (Object.keys(optimizer?.metadata?.optimized ?? {}).length) break;
  await new Promise((r) => setTimeout(r, 200));
}
report();
