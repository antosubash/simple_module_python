# Keep a response's own CSP (#870) — plan

Design: `docs/superpowers/specs/2026-11-07-response-csp-design.md` (approved).
All tasks are sequential and small.

1. **Tests first** — `framework/hosting/tests/test_hosting_csp_nonce.py`: a
   stricter non-sandbox policy is kept beside the nonced app policy; two
   response policies are both kept plus the app policy. Done when both fail on
   `main`'s middleware.
2. **Middleware** — `framework/hosting/simple_module_hosting/_security_headers.py`:
   append the app policy whenever the response already has a CSP header;
   drop the `sandbox` check. Done when the CSP tests pass.
3. **Docs + CHANGELOG** — `docs/framework/middleware.md`,
   `docs/module-authoring.md`, `docs/modules/file_storage.md`, `CHANGELOG.md`
   (Fixed, behaviour change, #870). Done when `make lint` passes.
