"""SimpleModule Host — entry point."""

import os
from pathlib import Path

# Publish the project root so the hosting layer can find host/static and
# host/templates whether we're running from the uv workspace or a wheel.
os.environ.setdefault(
    "SM_PROJECT_ROOT",
    str(Path(__file__).resolve().parent.parent),
)

from simple_module_hosting import Settings, create_app  # noqa: E402
from simple_module_hosting.logging import setup_logging  # noqa: E402

from host.routes import router as host_router  # noqa: E402

settings = Settings()

setup_logging(
    level=settings.log_level,
    json_format=settings.log_format == "json",
)

app = create_app(settings)
app.include_router(host_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
