{
  "name": "@simple-module-py/{{MODULE_SLUG}}",
  "version": "0.1.0",
  "private": true,
  "description": "Frontend assets for the {{MODULE_NAME}} module",
  "scripts": {
    "typecheck": "tsc --noEmit"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@inertiajs/react": "^2.0.0",
    "@simple-module-py/ui": "*"
  },
  "devDependencies": {
    "@inertiajs/react": "^2.0.0",
    "@simple-module-py/i18n": "{{FRAMEWORK_VERSION}}",
    "@simple-module-py/tsconfig": "{{FRAMEWORK_VERSION}}",
    "@simple-module-py/ui": "{{FRAMEWORK_VERSION}}",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "typescript": "^5.7.0"
  },
  "dependencies": {}
}
