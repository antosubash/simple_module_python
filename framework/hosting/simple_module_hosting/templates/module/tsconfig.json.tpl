{
  "extends": "@simple-module/tsconfig/base.json",
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./{{PACKAGE_NAME}}/*"],
      "@simple-module/ui/*": ["../../packages/ui/src/*"]
    }
  },
  "include": ["{{PACKAGE_NAME}}/**/*.ts", "{{PACKAGE_NAME}}/**/*.tsx"]
}
