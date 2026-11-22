"""Provider-neutral roles and fail-closed defaults (#953)."""

from types import SimpleNamespace

from simple_module_core.access.role_directory import (
    DirectoryRole,
    MappedRoleDirectory,
    NullRoleDirectory,
    RoleDirectory,
    get_role_directory,
    set_role_directory,
)


async def test_null_directory_knows_no_roles():
    app = SimpleNamespace(state=SimpleNamespace())
    directory = get_role_directory(app)
    assert isinstance(directory, NullRoleDirectory)
    assert isinstance(directory, RoleDirectory)
    assert not directory.editable
    assert await directory.list_roles(None) == []
    assert await directory.user_roles(None, "anyone") is None


async def test_mapped_roles_use_live_application_names():
    settings = SimpleNamespace(
        role_mapping={
            "realm-editor": "editor",
            "other": "editor",
            "owner": "tenant:owner",
            "admin": "admin",
        }
    )
    directory = MappedRoleDirectory(lambda: settings.role_mapping)
    app = SimpleNamespace(state=SimpleNamespace())
    set_role_directory(app, directory)
    assert get_role_directory(app) is directory
    assert isinstance(directory, RoleDirectory)
    assert await directory.list_roles(None) == [
        DirectoryRole("admin", "admin"),
        DirectoryRole("editor", "editor"),
    ]
    assert await directory.user_roles(None, "anyone") is None
    assert not directory.editable
    settings.role_mapping = {"new": "reader"}
    assert await directory.list_roles(None) == [DirectoryRole("reader", "reader")]
