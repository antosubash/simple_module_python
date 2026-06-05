# QA Report: Auth-gating (issue #191 public-routes extension point)

**Date:** 2026-06-05
**Tester:** Claude QA (Senior)
**Target:** http://localhost:8000 (API) + Vite :5050
**Depth:** scoped (backend middleware change — no new UI)
**Iteration:** 1 of 3

## Scope rationale

Issue #191 adds a method-aware public-route extension point to `AuthMiddleware`.
It is a **backend change with no new UI**. The risk surface is therefore not a
page to fuzz, but **which routes the middleware gates vs. lets through
anonymously**. This QA validates exactly that, in a real browser + at the HTTP
layer, including a live end-to-end exercise of the new mechanism.

## Summary
| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Public routes (anonymous load) | 3 | 0 | 0 |
| Protected-route gating | 2 | 0 | 0 |
| Login + authenticated access | 2 | 0 | 0 |
| New public-route mechanism (live) | 2 | 0 | 0 |
| **Total** | **9** | **0** | **0** |

## Critical / Major / Minor Issues
None.

## Observations (P3 — not bugs)
- **OBS-001** `GET /favicon.ico → 404` appears in the console on every page.
  Cosmetic, pre-existing, unrelated to #191 (no favicon shipped by the host).
- **OBS-002** Dev-workspace has both `users` and `keycloak` installed as entry
  points, so a bare boot trips `SM020` (multiple auth providers). Pre-existing,
  unrelated to #191; worked around by `SM_MODULES_ENABLED` excluding Keycloak
  (the same approach the existing test suite uses).

## Passed Tests
| # | Scenario | Result | Evidence |
|---|----------|--------|----------|
| TEST-001 | Public `/` loads anonymously | PASS | 00-landing-anonymous.png |
| TEST-002 | Public `/users/login` loads anonymously | PASS | 01-protected-redirects-to-login.png |
| TEST-003 | `/health` 200; `/api/users/auth/` 404 (passed gating) | PASS | curl smoke |
| TEST-004 | Protected `/dashboard` → 302 → login (anonymous) | PASS | 01-protected-redirects-to-login.png |
| TEST-005 | Protected API `/api/users/admin` → 401 (no redirect) | PASS | curl smoke |
| TEST-006 | Login as admin establishes session | PASS | 02-dashboard-authenticated.png |
| TEST-007 | Authenticated `/dashboard` renders | PASS | 02-dashboard-authenticated.png |
| TEST-008 | `SM_AUTH_PUBLIC_PATHS` flips gating live: 302 → 404 | PASS | 03-public-route-mechanism-404-not-redirect.png |
| TEST-009 | Control: unlisted path stays gated (302) | PASS | curl smoke |

## Verdict
**ALL CLEAN.** The #191 change preserves every existing auth-gating behavior
(public routes load anonymously; protected routes redirect/401; login works;
authenticated access works) and the new public-route mechanism works end-to-end
in the live app with no over-matching. No bugs found → no fix loop required.
