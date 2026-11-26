import json
import stat

import pytest
from simple_module_remote.config.paths import cache_dir
from simple_module_remote.schema.cache import (
    SchemaCacheError,
    load_cached,
    read_meta,
    touch_cache,
    write_cache,
)

CLI = "smdev"
ORIGIN = "https://app.example"
DOC = json.dumps({"openapi": "3.1.0", "info": {"version": "2"}, "paths": {}}).encode()


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_cache_dir_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "c"))
    assert cache_dir(CLI) == tmp_path / "c" / CLI
    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cache_dir(CLI) == tmp_path / "home" / ".cache" / CLI


def test_write_then_load_round_trips_with_private_modes():
    meta = write_cache(CLI, "dev", ORIGIN, DOC, 'W/"abc"')
    cached = load_cached(CLI, "dev", ORIGIN)
    assert cached is not None and cached.root["info"]["version"] == "2"
    assert cached.meta == meta and meta.etag == 'W/"abc"' and len(meta.fingerprint) == 64
    env_dir = cache_dir(CLI) / "dev"
    assert _mode(cache_dir(CLI)) == 0o700 and _mode(env_dir) == 0o700
    assert {p.name: _mode(p) for p in env_dir.iterdir()} == {
        "openapi.json": 0o600,
        "meta.json": 0o600,
    }


def test_missing_cache_is_none():
    assert load_cached(CLI, "dev", ORIGIN) is None


def test_origin_change_invalidates():
    write_cache(CLI, "dev", ORIGIN, DOC, None)
    with pytest.raises(SchemaCacheError, match=r"now points at https://other\.example"):
        load_cached(CLI, "dev", "https://other.example")


def test_altered_schema_is_refused():
    write_cache(CLI, "dev", ORIGIN, DOC, None)
    target = cache_dir(CLI) / "dev" / "openapi.json"
    target.write_bytes(DOC.replace(b'"2"', b'"3"'))
    with pytest.raises(SchemaCacheError, match="altered"):
        load_cached(CLI, "dev", ORIGIN)


def test_loose_or_symlinked_files_are_refused(tmp_path):
    write_cache(CLI, "dev", ORIGIN, DOC, None)
    meta = cache_dir(CLI) / "dev" / "meta.json"
    meta.chmod(0o644)
    with pytest.raises(SchemaCacheError, match="accessible to other users"):
        read_meta(CLI, "dev")
    elsewhere = tmp_path / "planted.json"
    elsewhere.write_bytes(meta.read_bytes())
    meta.unlink()
    meta.symlink_to(elsewhere)
    with pytest.raises(SchemaCacheError, match="symlink"):
        read_meta(CLI, "dev")


def test_corrupt_meta_is_refused():
    write_cache(CLI, "dev", ORIGIN, DOC, None)
    (cache_dir(CLI) / "dev" / "meta.json").write_text('{"origin": 1}')
    with pytest.raises(SchemaCacheError, match="corrupt"):
        read_meta(CLI, "dev")


@pytest.mark.parametrize("body", [b"[]", b"not json", b'{"openapi": "3.1.0"}', b'{"paths": {}}'])
def test_write_refuses_a_non_openapi_body(body):
    with pytest.raises(SchemaCacheError):
        write_cache(CLI, "dev", ORIGIN, body, None)
    assert not (cache_dir(CLI) / "dev").exists()


def test_touch_keeps_the_schema_and_moves_fetched_at():
    meta = write_cache(CLI, "dev", ORIGIN, DOC, "e1")
    old = meta.__class__(meta.origin, meta.fingerprint, meta.etag, "2020-01-01T00:00:00+00:00")
    fresh = touch_cache(CLI, "dev", old)
    assert fresh.fingerprint == meta.fingerprint and fresh.fetched_at != old.fetched_at
    assert read_meta(CLI, "dev") == fresh
    assert old.age_seconds() > 86400 and (fresh.age_seconds() or 0) < 60
