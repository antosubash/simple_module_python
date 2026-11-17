    def register_settings(self, app: FastAPI) -> None:
        from {{PACKAGE_NAME}}.core.services import {{MODULE_NAME}}Services
        from {{PACKAGE_NAME}}.core.settings import {{MODULE_NAME}}Settings

        # Records the class so the host hydrates it from the settings table
        # (DB → default) and mounts the services on app.state.{{PACKAGE_NAME}}.
        register_module_settings(
            app,
            "{{PACKAGE_NAME}}",
            {{MODULE_NAME}}Settings,
            lambda s: {{MODULE_NAME}}Services(settings=s),
        )

