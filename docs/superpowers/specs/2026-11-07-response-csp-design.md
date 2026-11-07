# Keep a response's own Content-Security-Policy (#870)

## Goal & scope

`SecurityHeadersMiddleware` replaces a response's `Content-Security-Policy`
with the app policy unless that policy contains `sandbox`. A module that wants
a *stricter* policy for one page (pagebuilder/news `public_csp` with
`frame-ancestors 'none'`) is silently ignored.

In scope: send every response-supplied CSP beside the app policy; tests; docs;
CHANGELOG.
Out of scope: `Content-Security-Policy-Report-Only` (already passed through
untouched), `X-Frame-Options` (still forced to `SAMEORIGIN`), a per-route API
for declaring policies.

## Approach

Chosen: drop the `sandbox` special case. When the response already carries one
or more CSP headers, keep them and **append** the app policy as another header.
Browsers enforce every policy, so the effective policy is the intersection: a
response can only tighten, never loosen, the app policy. This is the #785
guarantee extended to every response.

Rejected:
- Keep overwriting and log a warning — a module still cannot tighten a page,
  which is the actual need.
- Merge directives into one header — needs a CSP parser and intersection rules
  per source expression; two headers give the same result for free.

## Design

In `send_with_headers` (`framework/hosting/simple_module_hosting/_security_headers.py`):

- if the response has any `Content-Security-Policy` header → `headers.append(app_policy)`;
- otherwise → set the app policy as today.

The request nonce is inserted into the app policy only. The response's policy
is sent byte-for-byte; if it restricts `script-src` it must allow the page's
scripts itself (`'self'`, or `'nonce-{request.state.csp_nonce}'` for inline or
nonced scripts), because both policies apply. 304 handling is unchanged.

## Decisions made

- All responses, not just HTML: an API or file response with its own CSP gets
  the same treatment (file_storage's sandbox responses keep working
  identically).
- No log line: nothing is discarded any more.
- Behaviour change noted in CHANGELOG under Fixed: a response that set a
  *looser* policy (relying on the overwrite) now has it enforced alongside the
  app policy. A repo-wide grep finds only file_storage setting a CSP, and its
  policy contains `sandbox`, so nothing in this repo changes.

## Testing

`framework/hosting/tests/test_hosting_csp_nonce.py`:
- a non-sandbox stricter policy (`default-src 'self'; frame-ancestors 'none'`)
  → two headers, own policy unchanged, app policy carries the nonce;
- two policies set by the response → both kept plus the app policy;
- existing sandbox and 304 tests stay green;
- no response policy → exactly one header (existing tests cover this).

No browser QA: header-only change, covered by ASGI tests (`--skip-browser`).

## Docs

`docs/framework/middleware.md` § SecurityHeadersMiddleware (replace the
"overwritten" sentence), `docs/module-authoring.md` § External asset origins
(how to set a stricter page policy and the nonce caveat),
`docs/modules/file_storage.md` wording, CHANGELOG `## [Unreleased]` → Fixed.

## Risks

Low. A host-level code path that sets a CSP to *replace* the app policy would
now have both enforced; none exists in this repo, and the CHANGELOG flags it
for downstream hosts.
