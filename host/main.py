"""SimpleModule Host — entry point."""

from simple_module_hosting import Settings, create_app
from simple_module_hosting.logging import setup_logging

settings = Settings()

setup_logging(
    level=settings.log_level,
    json_format=settings.log_format == "json",
)

app = create_app(settings)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
