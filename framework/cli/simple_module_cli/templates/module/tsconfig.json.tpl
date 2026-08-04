{
  "extends": "@simple-module-py/tsconfig/base.json",
  "compilerOptions": {
    "paths": {
      "@/*": ["./{{PACKAGE_NAME}}/*"],
      "@simple-module-py/ui/*": ["../../packages/ui/src/*"]
    }
  },
  "include": ["{{PACKAGE_NAME}}/**/*.ts", "{{PACKAGE_NAME}}/**/*.tsx"]
}
