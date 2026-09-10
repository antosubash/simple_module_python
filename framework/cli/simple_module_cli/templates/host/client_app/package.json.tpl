{
  "name": "{{HOST_PYPI_NAME}}-client-app",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@inertiajs/react": "^2.0.0",
    "@simple-module-py/i18n": "{{FRAMEWORK_VERSION}}",
    "@simple-module-py/ui": "{{FRAMEWORK_VERSION}}",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@simple-module-py/tsconfig": "{{FRAMEWORK_VERSION}}",
    "@tailwindcss/vite": "^4.0.0",
    "@types/node": "^26.5.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^6.1.1",
    "tailwindcss": "^4.0.0",
    "typescript": "^7.0.2",
    "vite": "^8.2.2"
  }
}
