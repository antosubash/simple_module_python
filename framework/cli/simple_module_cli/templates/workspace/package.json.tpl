{
  "name": "{{HOST_PYPI_NAME}}",
  "private": true,
  "type": "module",
  "workspaces": [
    "host/client_app",
    "modules/*"
  ],
  "scripts": {
    "dev": "npm run --workspace host/client_app dev",
    "build": "npm run --workspace host/client_app build"
  }
}
