---
name: simple-module-conventions
description: Use when writing or reviewing code inside modules/ in a simple_module_python codebase, hitting type-check or lint failures in module code, or unsure which base class / settings prefix / file structure to use. Triggers on "add a model", "where do settings go", "why is doctor warning", or any edit under modules/.
---

# simple_module_python conventions

The framework relies on these invariants. Every rule here exists because something concrete breaks without it.

## The hard rules

### 1. SQLModel everywhere — both tables and DTOs

```python
from sqlmodel import Field, SQLModel
from simple_module_db.base import create_module_base

Base = create_module_base("orders")

class Order(Base, AuditMixin, table=True):           # table
    __tablename__ = "orders_order"
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)

class OrderOut(SQLModel):                            # DTO — plain SQLModel, no table=True
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
```

Forbidden in module code: `pydantic.BaseModel` for DTOs, and SQLAlchemy `DeclarativeBase` + `Mapped[...]` / `mapped_column(...)` for tables. Autogenerate, fixtures, Inertia serialization, and the shared mixins all assume the SQLModel metaclass.

### 2. The file-size cap

Treat 300 lines as the design pressure on every `.py`, `.ts`, and `.tsx` file (the reference codebase enforces this in CI). When you approach it, **split by responsibility** — don't golf comments and blank lines to squeeze under.

### 3. Per-module settings: `SM_<MODULE>_*` on `app.state.<module>`

```python
class UsersModule(ModuleBase):
    def register_settings(self, app: FastAPI) -> None:
        from users.settings import UsersSettings    # reads SM_USERS_* env
        from users.state import UsersState
        app.state.users = UsersState(settings=UsersSettings())
```

- Env-var prefix is **always** `SM_<MODULE_UPPER>_*`. Cross-module reads are discouraged by convention (no enforcement) — go through the registry or event bus instead.
- The state attribute key is the lowercase package name or the lowercased `meta.name` — the diagnostics check accepts either. For module package `auth` with `meta.name="Auth"`, `app.state.auth` works either way.
- If you override `register_settings` and don't add anything to `app.state.<module>`, `SM012` fires at dev boot.

### 4. Framework must not import from plugins

`framework/*` packages are not allowed to `import` from anything in `modules/*`. The doctor raises **SM009 ERROR** if it finds one.

Plugin → framework imports are fine; framework → plugin is the forbidden direction. If framework code seems to need a module's symbol, the symbol belongs in `simple_module_core` or `simple_module_hosting`.

### 5. Construct translated Zod schemas inside hooks, never at module scope

```tsx
// ❌ wrong — freezes against the locale active at first render, forever
const schema = z.object({
  name: z.string().min(1, t('products.validation.name_required')),
});

// ✅ right
export function useProductSchema() {
  const { t } = useT();
  return z.object({
    name: z.string().min(1, t('products.validation.name_required')),
  });
}
```

**Why:** `t()` resolves once when the schema is constructed. Module-scope construction = first-render-locale-only forever, no matter what the user switches to.

### 6. CSRF: rely on `SameSite=Lax`, don't add a token header

There is no CSRF token middleware. Starlette's default `SameSite=Lax` session cookie isn't attached to cross-site POST/PUT/DELETE, so forged form-submits are unauthenticated. Page-side `fetch()` calls don't need a token header.

### 7. Don't call `session.commit()` in service code

The per-request `get_db` dependency auto-commits when there are pending writes. `flush()` only when you need DB-assigned values mid-request. Manual `commit()` double-commits on success and breaks the no-writes-then-rollback optimization.

### 8. Locales: `<package>/locales/<lang>.json`, namespace = lowercase module name

Keys are flattened: `{"browse": {"title": "X"}}` under namespace `orders` becomes `orders.browse.title` at runtime. Pluralize with CLDR suffixes: `_zero / _one / _two / _few / _many / _other`. Only `_other` is required.

Locale-related diagnostics: SM013 (missing file), SM014 (missing keys vs default), SM015 (extra keys), SM016 (invalid JSON / non-string leaves).

### 9. Don't re-enable the silenced ty rules

Projects using the `ty` type checker should globally suppress `unresolved-attribute`, `unsupported-operator`, `unknown-argument`, `no-matching-overload`, and `invalid-argument-type` in `pyproject.toml`. SQLModel runtime-instruments fields as SQLAlchemy attributes, so the type checker can't see what's there. Real bugs surface in tests.

## Related skills

- **simple-module-database** — per-module Base, mixins, session lifecycle
- **simple-module-doctor** — what each `SMnnn` diagnostic code means and how to fix it
