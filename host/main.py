"""SimpleModule Host — entry point."""

from simple_module_hosting.host import build_host_app

app = build_host_app(__file__, routers=("host.routes:router",))

from simple_module_core.menu import MenuItem, MenuSection  # noqa: E402

from host.e2e_inertia import mount_if_development as mount_e2e_inertia_if_development  # noqa: E402

repo_url = "https://github.com/antosubash/simple_module_python"
app.state.sm.menu_registry.add_many(
    [
        MenuItem(
            label=label,
            label_key=f"ui.public_nav.{label_key}",
            url=url,
            section=MenuSection.NAVBAR,
            requires_auth=False,
        )
        for label, label_key, url in (
            ("Docs", "docs", f"{repo_url}#readme"),
            ("Modules", "modules", f"{repo_url}/tree/main/modules"),
            ("GitHub", "github", repo_url),
        )
    ]
)
# Fixture pages for tests/e2e/inertia/; development only.
mount_e2e_inertia_if_development(app, app.state.sm.settings)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=app.state.sm.settings.is_development,
    )
