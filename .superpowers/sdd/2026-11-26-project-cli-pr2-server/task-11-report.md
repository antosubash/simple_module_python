# Task 11 report

Added 409 cannot_suspend_own_tenant guard in tenants admin suspend for token principals pinned to the path tenant. Locale en/de + useTenantErrors + gen-i18n. Tests (3 new) in test_tenants_token_reach.py. Docs, CHANGELOG, plan ruling updated. Tenants tests 242 passed, credential matrix 11 passed, ruff/ty/doc-paths/hardcoded-strings clean. No API schema change (cli-schema not needed).
