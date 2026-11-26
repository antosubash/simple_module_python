"""Host entry point; installed modules are discovered by the framework."""

from simple_module_hosting.boot.host import build_host_app

app = build_host_app(__file__, app_name="{{HOST_NAME}}", routers=("routes:router",))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=app.state.sm.settings.is_development)
