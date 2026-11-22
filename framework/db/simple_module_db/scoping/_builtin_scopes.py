"""Built-in scope definitions; tenancy retains its engine policy and bypass context."""

from typing import Any

from simple_module_db.models.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.scoping.scopes import ScopeFilter
from simple_module_db.scoping.tenancy import current_tenant_id, is_all_tenants, missing_tenant_error


class _TenantScope(ScopeFilter):
    def bypassed(self, options: Any) -> bool:
        return super().bypassed(options) or is_all_tenants()

    def requires_context(self, owner: Any) -> bool:
        from sqlalchemy.orm import Session

        from simple_module_db.scoping._engine_policies import policy_of, session_policy

        policy = session_policy(owner) if isinstance(owner, Session) else policy_of(owner)
        return bool(policy is not None and policy.tenant_strict)

    def missing_error(self, entity: str, operation: str) -> Exception:
        return missing_tenant_error(entity, operation)

    def missing_criteria(self, target: Any) -> Any:
        return target.tenant_id.is_(None)


soft_delete_scope = ScopeFilter(
    name="soft_delete",
    applies_to=SoftDeleteMixin,
    criteria=lambda cls, ctx: cls.is_deleted.is_(False),
    context=lambda: True,
    bypass_option="include_deleted",
    column="is_deleted",
    reads_only=True,
)
tenant_scope = _TenantScope(
    name="tenant",
    applies_to=MultiTenantMixin,
    criteria=lambda cls, ctx: cls.tenant_id == ctx,
    context=current_tenant_id,
    bypass_option="all_tenants",
    column="tenant_id",
)
