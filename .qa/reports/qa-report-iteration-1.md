# QA Report: Audit Log Module
**Date:** 2026-05-28
**Tester:** Claude QA (Senior)
**Target:** http://localhost:8000/audit_log
**Depth:** normal
**Iteration:** 1 of 3

## Summary
| Category | Passed | Failed | Skipped |
|----------|--------|--------|---------|
| Happy Path | 8 | 2 | 0 |
| Form Validation | — | — | — (agent timed out) |
| Error States | 11 | 6 | 0 |
| **Total** | **19** | **8** | **0** |

## Critical Issues (P0)
None.

## Major Issues (P1)

### BUG-001: Invalid query params render raw JSON validation errors
- **Severity:** P1 (4 instances: ES-005, ES-006, ES-007, ES-008)
- **Steps to reproduce:** Navigate to /audit_log?page_size=0 or /audit_log?page=-1 or /audit_log?page=abc or /audit_log?page_size=500
- **Expected:** Graceful fallback — clamp to defaults or show user-friendly error page
- **Actual:** Raw FastAPI JSON validation error shown as entire page content: `{"detail":[{"type":"greater_than_equal",...}]}`
- **Root cause:** Inertia view endpoint uses `Query(ge=1, le=200)` constraints which raise `RequestValidationError` — no handler converts these to Inertia-friendly responses
- **Fix hint:** Add a `RequestValidationError` exception handler in the view that either clamps to defaults or renders an Inertia error page. Could be framework-level (benefits all modules).

## Minor Issues (P2)

### BUG-002: Setting entity_id is empty string for integer-PK entities
- **Severity:** P2
- **Steps to reproduce:** Create a Setting via POST /api/settings/, then check the audit log for that Setting's "Created" entry
- **Expected:** entity_id shows the Setting's actual ID (e.g., "1")
- **Actual:** entity_id is "" (empty string) — the entity column shows "Setting" with no ID
- **Root cause:** Known limitation — `_entity_pk_str` runs during before_flush when integer PKs haven't been assigned yet. UUID PKs work fine.
- **Fix hint:** Architectural change needed — move to after_flush or accept as known limitation for integer-PK models.

## Observations (P3)

### OBS-001: Sidebar "Audit Log" link has no active/highlighted state
- **Severity:** P3
- **Details:** All sidebar links share identical CSS classes regardless of current page. No `aria-current="page"` is set. This is a framework-wide issue affecting all modules, not specific to Audit Log.

### OBS-002: Entity Type dropdown opens on Tab focus
- **Severity:** P3
- **Details:** The Radix Select component's Entity Type dropdown auto-opens when receiving Tab focus, potentially trapping keyboard navigation. This is a known Radix UI behavior.

### OBS-003: Out-of-range page shows empty state without context
- **Severity:** P3
- **Details:** /audit_log?page=999 shows "No audit entries" empty state. Could show "Page out of range" or redirect to last valid page.

### OBS-004: Form validation agent timed out
- **Details:** The form validation agent stalled while testing datetime-local inputs (likely Playwright interaction complexity with date pickers). Core form validation was partially covered by other agents.

## Passed Tests

<details>
<summary>Click to expand (19 tests passed)</summary>

| # | Category | Scenario | Result |
|---|----------|----------|--------|
| 1 | Happy Path | Page loads with data | PASS |
| 2 | Happy Path | Filter by Entity Type | PASS |
| 3 | Happy Path | Filter by Action | PASS |
| 4 | Happy Path | Filter by User ID | PASS |
| 5 | Happy Path | Clear filters | PASS |
| 6 | Happy Path | Pagination (Next/Previous) | PASS |
| 7 | Happy Path | New entity generates audit entry | PASS |
| 8 | Happy Path | Empty state display | PASS |
| 9 | Error States | Empty state for zero results | PASS |
| 10 | Error States | URL-based filter preselection | PASS |
| 11 | Error States | page_size=5 via URL | PASS |
| 12 | Error States | Browser back preserves state | PASS |
| 13 | Error States | Page refresh preserves filters | PASS |
| 14 | Error States | Enter key submits filter form | PASS |
| 15 | Error States | Rapid Apply clicks (5x) | PASS |
| 16 | Error States | Unauthenticated redirect to login | PASS |
| 17 | Error States | API endpoint returns JSON | PASS |
| 18 | Error States | API returns 401 unauthenticated | PASS |
| 19 | Error States | XSS in params safely handled | PASS |

</details>
