# @simple-module-py/tsconfig

Shared TypeScript compiler options for [simple_module](https://github.com/antosubash/simple_module_python) apps. One `base.json` that every `tsconfig.json` in the framework and its modules extends.

## Install

```bash
npm install --save-dev @simple-module-py/tsconfig
```

## What it provides

- `base.json` — the canonical compiler options for simple_module apps. Targets ES2022, `strict: true`, `module: "ESNext"`, `moduleResolution: "bundler"`, JSX `react-jsx`, `allowImportingTsExtensions: true`, `verbatimModuleSyntax: true`.

## Usage

In your app's `tsconfig.json`:

```json
{
  "extends": "@simple-module-py/tsconfig/base.json",
  "include": ["client_app/**/*.ts", "client_app/**/*.tsx"]
}
```

Override any option as needed — `extends` merges.

## Depends on

Nothing. This is a pure JSON config package.

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
