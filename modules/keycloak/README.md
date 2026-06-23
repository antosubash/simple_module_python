# simple_module_keycloak

Keycloak OIDC authentication provider for simple_module. Swap with `simple_module_users` for Keycloak-backed identity management — users, roles, and login all handled by Keycloak.

## Install

Add to your app's `pyproject.toml` dependencies instead of `simple_module_users`:

```toml
dependencies = [
    "simple_module_keycloak==0.0.17",
]
```

Run `uv sync --all-packages` to install.

## Usage

Set the required environment variables (or configure via the settings admin UI after first boot):

```bash
SM_KEYCLOAK_SERVER_URL=https://keycloak.example.com
SM_KEYCLOAK_REALM=my-realm
SM_KEYCLOAK_CLIENT_ID=my-app
SM_KEYCLOAK_CLIENT_SECRET=my-secret
```

The module auto-registers as the auth provider. Browser users are redirected to Keycloak's hosted login page. Mobile clients authenticate directly with Keycloak and send bearer tokens to the framework API.

Keycloak realm roles are mapped to framework permissions via the `role_mapping` setting (default: `admin` and `user` map 1:1).
