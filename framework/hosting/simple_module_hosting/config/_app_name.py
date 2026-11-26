"""App-local identity defaults, below environment and stored settings."""

from copy import deepcopy

from pydantic import create_model

from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.config.settings import Settings


def with_api_title_default[T: HostSettings](cls: type[T], app_name: str | None) -> type[T]:
    if app_name is None:
        return cls
    # Preserve restart/UI metadata and never mutate another app's defaults.
    title = deepcopy(cls.model_fields["api_title"])
    title.default = app_name
    return create_model(cls.__name__, __base__=cls, api_title=(str, title))


def resolve_app_settings(settings: Settings | None, app_name: str | None) -> Settings:
    from simple_module_hosting.config._preapp_config import merge_host_settings

    if settings is None:
        return merge_host_settings(app_name=app_name)
    if app_name is None:
        return settings
    # Explicit Settings values (including env/DB) keep their existing priority.
    updates = {} if "api_title" in settings.model_fields_set else {"api_title": app_name}
    settings = settings.model_copy(update=updates)
    settings._app_name_default = app_name
    return settings
