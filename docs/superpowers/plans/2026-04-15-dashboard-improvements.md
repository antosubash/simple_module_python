# Dashboard Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder dashboard with real user/product counts and a system info panel.

**Architecture:** The dashboard stats endpoint queries the `users_user` and `products_product` tables directly for counts, calls `discover_modules()` for module list, and runs health checks from `app.state.health_registry`. All data is passed as Inertia page props — no separate client-side fetch. The in-memory product event counters are removed.

**Tech Stack:** FastAPI, SQLAlchemy (async), Inertia.js/React 19, Tailwind CSS 4, lucide-react icons

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `modules/dashboard/dashboard/stats.py` | Create | Stats-fetching logic (DB queries, system info) |
| `modules/dashboard/dashboard/endpoints/api.py` | Modify | Call `fetch_dashboard_stats`, return full stats |
| `modules/dashboard/dashboard/endpoints/views.py` | Modify | Pass stats as Inertia props |
| `modules/dashboard/dashboard/handlers.py` | Delete | Remove in-memory product event counters |
| `modules/dashboard/dashboard/module.py` | Modify | Remove event subscriptions, add Users dependency |
| `modules/dashboard/dashboard/pages/Home.tsx` | Rewrite | Stat cards with real data + system info panel |
| `modules/dashboard/dashboard/locales/en.json` | Modify | Add new i18n keys |
| `modules/dashboard/dashboard/locales/es.json` | Modify | Add new i18n keys |
| `modules/dashboard/pyproject.toml` | Modify | Add `users` dependency |
| `modules/dashboard/tests/test_dashboard.py` | Rewrite | Tests for new stats endpoint and module registration |

---

### Task 1: Add `users` dependency to dashboard module

**Files:**
- Modify: `modules/dashboard/pyproject.toml`
- Modify: `modules/dashboard/dashboard/module.py`

- [ ] **Step 1: Add `users` to pyproject.toml dependencies**

In `modules/dashboard/pyproject.toml`, add `"users"` to both `[project] dependencies` and `[tool.uv.sources]`:

```toml
[project]
dependencies = [
    "simple-module-core",
    "simple-module-db",
    "simple-module-hosting",
    "products",
    "users",
]

[tool.uv.sources]
simple-module-core = { workspace = true }
simple-module-db = { workspace = true }
simple-module-hosting = { workspace = true }
products = { workspace = true }
users = { workspace = true }
```

- [ ] **Step 2: Update module metadata to depend on Users**

In `modules/dashboard/dashboard/module.py`, change `depends_on`:

```python
class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        depends_on=["Products", "Users"],
    )
```

- [ ] **Step 3: Remove event handler registration from module**

In `modules/dashboard/dashboard/module.py`, remove the `register_event_handlers` method entirely, and remove the imports of `on_product_created`, `on_product_deleted`, `on_product_updated` from `dashboard.handlers`, and the imports of `ProductCreated`, `ProductDeleted`, `ProductUpdated` from `products.contracts.events`, and the import of `EventBus` from `simple_module_core.events`.

The resulting `module.py`:

```python
"""Dashboard module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta


class DashboardModule(ModuleBase):
    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        depends_on=["Products", "Users"],
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from dashboard.endpoints.api import router as api
        from dashboard.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Dashboard",
                url="/dashboard",
                icon="home",
                order=1,
                section=MenuSection.SIDEBAR,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        return {"dashboard": Path(str(importlib.resources.files(__package__) / "locales"))}
```

- [ ] **Step 4: Delete handlers.py**

Delete the file `modules/dashboard/dashboard/handlers.py` entirely — the in-memory counters are no longer used.

- [ ] **Step 5: Commit**

```bash
git add modules/dashboard/pyproject.toml modules/dashboard/dashboard/module.py
git rm modules/dashboard/dashboard/handlers.py
git commit -m "refactor(dashboard): remove in-memory event counters, add Users dependency"
```

---

### Task 2: Create stats-fetching backend logic

**Files:**
- Create: `modules/dashboard/dashboard/stats.py`
- Test: `modules/dashboard/tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test for `fetch_dashboard_stats`**

Replace the contents of `modules/dashboard/tests/test_dashboard.py` with:

```python
"""Tests for the Dashboard module: stats endpoint and module registration."""

from __future__ import annotations

import httpx
import pytest
from dashboard.module import DashboardModule


# ── Module registration tests ────────────────────────────────────────


class TestDashboardModuleRegistration:
    async def test_module_meta(self):
        mod = DashboardModule()
        assert mod.meta.name == "Dashboard"
        assert mod.meta.route_prefix == "/api/dashboard"
        assert "Products" in mod.meta.depends_on
        assert "Users" in mod.meta.depends_on


# ── Stats function unit tests ────────────────────────────────────────


class TestFetchDashboardStats:
    async def test_returns_expected_keys(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert "total_users" in stats
        assert "active_users_7d" in stats
        assert "total_products" in stats
        assert "module_count" in stats
        assert "system_info" in stats

    async def test_total_users_counts_seeded_users(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        # The app fixture seeds at least one admin user via authenticated_client deps,
        # but fetch_dashboard_stats only counts what's in the DB at call time.
        assert isinstance(stats["total_users"], int)
        assert stats["total_users"] >= 0

    async def test_module_count_is_positive(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert stats["module_count"] >= 1

    async def test_system_info_contains_modules_list(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        sys_info = stats["system_info"]
        assert "modules" in sys_info
        assert isinstance(sys_info["modules"], list)
        assert len(sys_info["modules"]) >= 1
        assert "name" in sys_info["modules"][0]
        assert "status" in sys_info["modules"][0]

    async def test_system_info_contains_python_version(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert "python_version" in stats["system_info"]
        assert "." in stats["system_info"]["python_version"]

    async def test_system_info_contains_health_checks(self, app):
        from dashboard.stats import fetch_dashboard_stats

        async with app.state.db.session_factory() as db:
            stats = await fetch_dashboard_stats(db, app)

        assert "health_checks" in stats["system_info"]
        assert isinstance(stats["system_info"]["health_checks"], list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest modules/dashboard/tests/test_dashboard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'dashboard.stats'`

- [ ] **Step 3: Implement `fetch_dashboard_stats`**

Create `modules/dashboard/dashboard/stats.py`:

```python
"""Dashboard statistics queries."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from products.models import Product
from simple_module_core.discovery import discover_modules
from simple_module_core.health import HealthStatus
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from users.models import User


async def fetch_dashboard_stats(db: AsyncSession, app: FastAPI) -> dict:
    """Gather all dashboard statistics in a single call."""
    total_users = await _count_users(db)
    active_users_7d = await _count_active_users(db, days=7)
    total_products = await _count_products(db)
    module_count, modules_list = _get_module_info()
    health_checks = await _run_health_checks(app)

    return {
        "total_users": total_users,
        "active_users_7d": active_users_7d,
        "total_products": total_products,
        "module_count": module_count,
        "system_info": {
            "modules": modules_list,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "health_checks": health_checks,
        },
    }


async def _count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def _count_active_users(db: AsyncSession, *, days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(func.count()).select_from(User).where(User.last_login_at >= cutoff)
    )
    return result.scalar_one()


async def _count_products(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(Product).where(Product.is_active.is_(True))
    )
    return result.scalar_one()


def _get_module_info() -> tuple[int, list[dict[str, str]]]:
    modules = discover_modules()
    modules_list = [{"name": m.meta.name, "status": "loaded"} for m in modules]
    return len(modules), modules_list


async def _run_health_checks(app: FastAPI) -> list[dict[str, str]]:
    registry = app.state.health_registry
    results = []
    for check in registry.all_checks:
        try:
            result = await check.check()
            results.append({"name": check.name, "status": result.status.value})
        except Exception:
            results.append({"name": check.name, "status": HealthStatus.UNHEALTHY.value})
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest modules/dashboard/tests/test_dashboard.py -v`
Expected: All `TestFetchDashboardStats` tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/dashboard/dashboard/stats.py modules/dashboard/tests/test_dashboard.py
git commit -m "feat(dashboard): add stats-fetching logic with real DB queries"
```

---

### Task 3: Update stats API endpoint

**Files:**
- Modify: `modules/dashboard/dashboard/endpoints/api.py`
- Test: `modules/dashboard/tests/test_dashboard.py`

- [ ] **Step 1: Add API endpoint tests**

Append to `modules/dashboard/tests/test_dashboard.py`:

```python
# ── Stats API endpoint ──────────────────────────────────────────────


class TestDashboardStatsEndpoint:
    async def test_stats_returns_all_fields(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/dashboard/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_users" in body
        assert "active_users_7d" in body
        assert "total_products" in body
        assert "module_count" in body
        assert "system_info" in body

    async def test_stats_total_users_includes_seeded_admin(
        self, authenticated_client: httpx.AsyncClient
    ):
        resp = await authenticated_client.get("/api/dashboard/stats")
        body = resp.json()
        # authenticated_client fixture seeds one admin user
        assert body["total_users"] >= 1

    async def test_stats_system_info_has_modules(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/dashboard/stats")
        body = resp.json()
        modules = body["system_info"]["modules"]
        assert len(modules) >= 1
        names = [m["name"] for m in modules]
        assert "Dashboard" in names

    async def test_stats_requires_authentication(self, client: httpx.AsyncClient):
        resp = await client.get("/api/dashboard/stats", follow_redirects=False)
        assert resp.status_code in (302, 401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest modules/dashboard/tests/test_dashboard.py::TestDashboardStatsEndpoint -v`
Expected: FAIL — old endpoint returns `{"product_events": ...}` shape

- [ ] **Step 3: Update the stats endpoint**

Replace `modules/dashboard/dashboard/endpoints/api.py` with:

```python
"""REST API endpoints for the Dashboard module."""

from __future__ import annotations

from fastapi import APIRouter, Request
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.stats import fetch_dashboard_stats

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Return dashboard statistics including user counts and system info."""
    return await fetch_dashboard_stats(db, request.app)
```

Note: add `from fastapi import APIRouter, Depends, Request` (include `Depends`).

Corrected file:

```python
"""REST API endpoints for the Dashboard module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from simple_module_db.deps import get_db
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.stats import fetch_dashboard_stats

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Return dashboard statistics including user counts and system info."""
    return await fetch_dashboard_stats(db, request.app)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest modules/dashboard/tests/test_dashboard.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add modules/dashboard/dashboard/endpoints/api.py modules/dashboard/tests/test_dashboard.py
git commit -m "feat(dashboard): expand /stats endpoint with real counts and system info"
```

---

### Task 4: Update Inertia view endpoint to pass stats as props

**Files:**
- Modify: `modules/dashboard/dashboard/endpoints/views.py`

- [ ] **Step 1: Update the view endpoint**

Replace `modules/dashboard/dashboard/endpoints/views.py` with:

```python
"""Inertia view endpoints for the Dashboard.

Mounted under ``/dashboard`` via :attr:`DashboardModule.meta.view_prefix`.
The public landing page at ``/`` is owned by the host, not this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from inertia import InertiaResponse
from simple_module_db.deps import get_db
from simple_module_hosting.i18n_deps import TranslatorDep
from simple_module_hosting.inertia_deps import InertiaDep
from sqlalchemy.ext.asyncio import AsyncSession

from dashboard.stats import fetch_dashboard_stats

router = APIRouter()


@router.get("/", response_model=None)
async def dashboard(
    request: Request,
    inertia: InertiaDep,
    t: TranslatorDep,
    db: AsyncSession = Depends(get_db),
) -> InertiaResponse:
    """Authenticated dashboard — requires login (enforced by AuthMiddleware)."""
    stats = await fetch_dashboard_stats(db, request.app)
    return await inertia.render(
        "Dashboard/Home",
        {
            "welcome": t.t("dashboard.home.welcome_message"),
            **stats,
        },
    )
```

- [ ] **Step 2: Run full test suite to verify nothing breaks**

Run: `python -m pytest modules/dashboard/tests/test_dashboard.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add modules/dashboard/dashboard/endpoints/views.py
git commit -m "feat(dashboard): pass real stats as Inertia props to Home page"
```

---

### Task 5: Update i18n locale files

**Files:**
- Modify: `modules/dashboard/dashboard/locales/en.json`
- Modify: `modules/dashboard/dashboard/locales/es.json`

- [ ] **Step 1: Update English locale**

Replace `modules/dashboard/dashboard/locales/en.json` with:

```json
{
  "home": {
    "title": "Dashboard",
    "description": "Overview of your application",
    "stats": {
      "total_users": "Total Users",
      "active_users": "Active Users (7d)",
      "products": "Products",
      "modules": "Modules"
    },
    "system_info_title": "System",
    "system_info": {
      "modules": "Modules",
      "python_version": "Python Version",
      "health_checks": "Health Checks"
    },
    "welcome_card_title": "Welcome",
    "welcome_message": "Welcome to SimpleModule",
    "description_body": "This is a modular monolith built with FastAPI, Inertia.js, and React. Each module provides its own pages, API endpoints, and database schema."
  }
}
```

- [ ] **Step 2: Update Spanish locale**

Replace `modules/dashboard/dashboard/locales/es.json` with:

```json
{
  "home": {
    "title": "Panel",
    "description": "Resumen de tu aplicación",
    "stats": {
      "total_users": "Usuarios Totales",
      "active_users": "Usuarios Activos (7d)",
      "products": "Productos",
      "modules": "Módulos"
    },
    "system_info_title": "Sistema",
    "system_info": {
      "modules": "Módulos",
      "python_version": "Versión de Python",
      "health_checks": "Verificaciones de Salud"
    },
    "welcome_card_title": "Bienvenido",
    "welcome_message": "Bienvenido a SimpleModule",
    "description_body": "Este es un monolito modular construido con FastAPI, Inertia.js y React. Cada módulo proporciona sus propias páginas, endpoints de API y esquema de base de datos."
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add modules/dashboard/dashboard/locales/en.json modules/dashboard/dashboard/locales/es.json
git commit -m "feat(dashboard): add i18n keys for new stat cards and system info"
```

---

### Task 6: Rewrite Home.tsx frontend

**Files:**
- Rewrite: `modules/dashboard/dashboard/pages/Home.tsx`

- [ ] **Step 1: Rewrite Home.tsx with real stats and system info panel**

Replace `modules/dashboard/dashboard/pages/Home.tsx` with:

```tsx
import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { PageShell } from '@simple-module-py/ui/components/PageShell';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@simple-module-py/ui/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from '@simple-module-py/ui/components/ui/table';
import { AuthenticatedLayout } from '@simple-module-py/ui/layouts/AuthenticatedLayout';
import { Activity, Box, Heart, Package, Server, Users } from 'lucide-react';

interface SystemModule {
  name: string;
  status: string;
}

interface HealthCheck {
  name: string;
  status: string;
}

interface SystemInfo {
  modules: SystemModule[];
  python_version: string;
  health_checks: HealthCheck[];
}

interface Props {
  welcome: string;
  total_users: number;
  active_users_7d: number;
  total_products: number;
  module_count: number;
  system_info: SystemInfo;
}

function Home() {
  const props = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  return (
    <PageShell
      title={t(keys.dashboard.home.title)}
      description={t(keys.dashboard.home.description)}
    >
      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-5 mb-8">
        <StatCard
          title={t(keys.dashboard.home.stats.total_users)}
          value={String(props.total_users)}
          icon={<Users className="size-4" />}
          accent="emerald"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.active_users)}
          value={String(props.active_users_7d)}
          icon={<Activity className="size-4" />}
          accent="amber"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.products)}
          value={String(props.total_products)}
          icon={<Package className="size-4" />}
          accent="primary"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.modules)}
          value={String(props.module_count)}
          icon={<Box className="size-4" />}
          accent="violet"
        />
      </div>

      {/* System Info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-[var(--font-display)]">
            <Server className="size-4" />
            {t(keys.dashboard.home.system_info_title)}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Modules */}
          <div>
            <h4 className="text-sm font-medium text-muted-foreground mb-2">
              {t(keys.dashboard.home.system_info.modules)}
            </h4>
            <div className="flex flex-wrap gap-2">
              {props.system_info.modules.map((mod) => (
                <span
                  key={mod.name}
                  className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium"
                >
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {mod.name}
                </span>
              ))}
            </div>
          </div>

          {/* Python Version + Health Checks */}
          <Table>
            <TableBody>
              <TableRow>
                <TableCell className="font-medium text-muted-foreground">
                  {t(keys.dashboard.home.system_info.python_version)}
                </TableCell>
                <TableCell>{props.system_info.python_version}</TableCell>
              </TableRow>
              {props.system_info.health_checks.map((check) => (
                <TableRow key={check.name}>
                  <TableCell className="font-medium text-muted-foreground flex items-center gap-2">
                    <Heart className="size-3" />
                    {check.name}
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className={`size-2 rounded-full ${
                          check.status === 'healthy'
                            ? 'bg-emerald-500'
                            : check.status === 'degraded'
                              ? 'bg-amber-500'
                              : 'bg-red-500'
                        }`}
                      />
                      {check.status}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </PageShell>
  );
}

function StatCard({
  title,
  value,
  icon,
  accent,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  accent: string;
}) {
  const styles: Record<string, { card: string; icon: string; value: string }> = {
    primary: {
      card: 'border-primary-200 bg-gradient-to-br from-primary-50 to-card',
      icon: 'text-primary-500 bg-primary-100',
      value: 'text-primary-900',
    },
    emerald: {
      card: 'border-emerald-border bg-gradient-to-br from-emerald-bg to-card',
      icon: 'text-emerald-icon-fg bg-emerald-icon-bg',
      value: 'text-emerald-value',
    },
    violet: {
      card: 'border-violet-border bg-gradient-to-br from-violet-bg to-card',
      icon: 'text-violet-icon-fg bg-violet-icon-bg',
      value: 'text-violet-value',
    },
    amber: {
      card: 'border-amber-200 bg-gradient-to-br from-amber-50 to-card',
      icon: 'text-amber-600 bg-amber-100',
      value: 'text-amber-900',
    },
  };

  const s = styles[accent] || styles.primary;

  return (
    <Card className={s.card}>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-muted-foreground">{title}</span>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${s.icon}`}>
            {icon}
          </div>
        </div>
        <p className={`text-3xl font-bold font-[var(--font-display)] ${s.value}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;
```

- [ ] **Step 2: Verify the frontend builds**

Run: `npm run build --workspace=host` (or the project's build command)
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add modules/dashboard/dashboard/pages/Home.tsx
git commit -m "feat(dashboard): rewrite Home page with real stats and system info panel"
```

---

### Task 7: Run full test suite and fix any issues

- [ ] **Step 1: Run all dashboard tests**

Run: `python -m pytest modules/dashboard/tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run integration tests that touch dashboard**

Run: `python -m pytest tests/integration/ -v -k "dashboard or product"`
Expected: All tests PASS (product integration tests that checked old `product_events` key will fail — see next step)

- [ ] **Step 3: Fix integration tests if needed**

The old integration tests in `modules/dashboard/tests/test_dashboard.py` that referenced `product_events` are already replaced in Task 2. But `tests/integration/test_products_journey.py` may reference the old stats shape. Check and update if needed.

Run: `python -m pytest tests/integration/test_products_journey.py -v`

- [ ] **Step 4: Run linter**

Run: `ruff check modules/dashboard/`
Expected: No errors

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix(dashboard): resolve test and lint issues from dashboard rewrite"
```
