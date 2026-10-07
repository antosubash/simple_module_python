"""SimpleModule Host — entry point."""

import os
from pathlib import Path

from simple_module_core.dotenv import load_dotenv_into_environ

# Publish ``SM_PROJECT_ROOT`` and merge ``.env`` into ``os.environ`` *before*
# any settings import so framework code reading ``os.environ.get("SM_…")``
# directly (not via pydantic-settings) sees the same values pydantic does —
# keeping precedence (real env wins) consistent across the web process, the
# worker, and one-shot scripts.
os.environ.setdefault("SM_PROJECT_ROOT", str(Path(__file__).resolve().parent.parent))
load_dotenv_into_environ(Path(os.environ["SM_PROJECT_ROOT"]) / ".env")

from simple_module_hosting import create_app, merge_host_settings  # noqa: E402
from simple_module_hosting.logging import setup_logging  # noqa: E402

from host.routes import router as host_router  # noqa: E402
from host.routes_i18n import router as i18n_router  # noqa: E402
from host.routes_legacy import router as legacy_router  # noqa: E402

# merge_host_settings, not Settings(): log_level and the rest of the host
# knobs live in the DB now. create_app falls back to this when passed no
# settings, but it is passed settings here — so the read has to happen at
# this call site or it never happens in the real host at all.
settings = merge_host_settings()

setup_logging(
    level=settings.log_level,
    json_format=settings.log_format == "json",
)

app = create_app(settings)
app.include_router(host_router)
app.include_router(i18n_router)
# Mounted last: its catch-all {path:path} routes must not shadow a real
# route that happens to share a legacy prefix.
app.include_router(legacy_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
    )
