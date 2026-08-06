{
  "extends": "@simple-module-py/tsconfig/base.json",
  "compilerOptions": {
    "paths": {
      "@/*": ["./{{PACKAGE_NAME}}/*"],
      "@simple-module-py/ui/*": ["../../node_modules/@simple-module-py/ui/src/*"]
    }
  },
  "include": ["{{PACKAGE_NAME}}/**/*.ts", "{{PACKAGE_NAME}}/**/*.tsx"]
}
