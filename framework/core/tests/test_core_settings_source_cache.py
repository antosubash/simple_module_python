"""Settings source metadata is a process snapshot, isolated by settings class."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from simple_module_core.settings_hydrate import env_supplied_fields


def test_source_fields_are_computed_once_per_class(tmp_path, monkeypatch):
    dotenv = tmp_path / "settings.env"
    dotenv.write_text("CACHE_FILE=file\n")
    monkeypatch.setenv("CACHE_PROCESS", "process")
    calls = []

    class Config(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="CACHE_", env_file=dotenv)
        process: str = ""
        file: str = ""
        seeded: str = ""
        alias: str = Field("", alias="CACHE_ALIAS")

        @classmethod
        def settings_customise_sources(cls, *args, **kwargs):
            calls.append("sources")
            return super().settings_customise_sources(*args, **kwargs)

        @classmethod
        def env_seeded_fields(cls):
            calls.append("seeded")
            return {"seeded", "unknown"}

    monkeypatch.setenv("CACHE_ALIAS", "alias")
    assert env_supplied_fields(Config) == {"process", "file", "seeded", "alias"}
    assert isinstance(env_supplied_fields(Config), frozenset)
    dotenv.unlink()
    monkeypatch.delenv("CACHE_PROCESS")
    monkeypatch.delenv("CACHE_ALIAS")
    assert env_supplied_fields(Config) == {"process", "file", "seeded", "alias"}
    assert calls == ["sources", "seeded"]

    class Other(Config):
        @classmethod
        def env_seeded_fields(cls):
            return set()

    assert env_supplied_fields(Other) == set()
