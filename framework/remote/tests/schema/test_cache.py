import json
import stat

import pytest
from simple_module_remote.config import _private_dir
from simple_module_remote.config.paths import cache_dir
from simple_module_remote.schema import cache as cache_mod
from simple_module_remote.schema.cache import (
    SchemaCacheError,
    load_cached,
    open_cache,
    read_meta,
    touch_in,
    write_to,
)

CLI = "smdev"
URL = "https://app.example/base"
ORIGIN = "https://app.example"
DOC = json.dumps({"openapi": "3.1.0", "info": {"version": "2"}, "paths": {}}).encode()


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _write(env="dev", data=DOC, etag=None, url=URL):
    with open_cache(CLI, env, create=True) as store:
        return write_to(store, url, ORIGIN, data, etag)


def _meta(env="dev"):
    with open_cache(CLI, env, create=False) as store:
        return read_meta(store)


def test_cache_dir_follows_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "c"))
    assert cache_dir(CLI) == tmp_path / "c" / CLI
    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    assert cache_dir(CLI) == tmp_path / "home" / ".cache" / CLI


def test_write_then_load_round_trips_with_private_modes():
    meta = _write(etag='W/"abc"')
    cached = load_cached(CLI, "dev", URL, ORIGIN)
    assert cached is not None and cached.root["info"]["version"] == "2"
    assert cached.meta == meta and meta.etag == 'W/"abc"' and len(meta.fingerprint) == 64
    assert meta.url == URL
    env_dir = cache_dir(CLI) / "dev"
    assert _mode(cache_dir(CLI)) == 0o700 and _mode(env_dir) == 0o700
    assert {p.name: _mode(p) for p in env_dir.iterdir()} == {
        "openapi.json": 0o600,
        "meta.json": 0o600,
    }


def test_missing_cache_is_none():
    assert load_cached(CLI, "dev", URL, ORIGIN) is None
    assert not cache_dir(CLI).exists()  # reading never creates directories


def test_url_change_invalidates_including_the_path():
    _write()
    with pytest.raises(SchemaCacheError, match=r"now points at https://other\.example"):
        load_cached(CLI, "dev", "https://other.example", "https://other.example")
    with pytest.raises(SchemaCacheError, match="now points at"):
        load_cached(CLI, "dev", "https://app.example/other", ORIGIN)


def test_altered_schema_is_refused():
    _write()
    target = cache_dir(CLI) / "dev" / "openapi.json"
    target.write_bytes(DOC.replace(b'"2"', b'"3"'))
    with pytest.raises(SchemaCacheError, match="altered"):
        load_cached(CLI, "dev", URL, ORIGIN)


def test_loose_or_symlinked_files_are_refused(tmp_path):
    _write()
    meta = cache_dir(CLI) / "dev" / "meta.json"
    meta.chmod(0o644)
    with pytest.raises(SchemaCacheError, match="accessible to other users"):
        _meta()
    elsewhere = tmp_path / "planted.json"
    elsewhere.write_bytes(meta.read_bytes())
    meta.unlink()
    meta.symlink_to(elsewhere)
    with pytest.raises(SchemaCacheError, match="symlink"):
        _meta()


def test_symlinked_env_dir_is_refused_for_reads_and_writes(tmp_path):
    planted = tmp_path / "planted"
    planted.mkdir(mode=0o700)
    cache_dir(CLI).mkdir(parents=True, mode=0o700)
    (cache_dir(CLI) / "dev").symlink_to(planted)
    with pytest.raises(SchemaCacheError, match="not a plain directory"):
        load_cached(CLI, "dev", URL, ORIGIN)
    with pytest.raises(SchemaCacheError, match="not a plain directory"):
        _write()
    assert list(planted.iterdir()) == []


def test_loose_dir_is_tightened_and_foreign_dir_refused(monkeypatch):
    _write()
    env_dir = cache_dir(CLI) / "dev"
    env_dir.chmod(0o755)
    assert load_cached(CLI, "dev", URL, ORIGIN) is not None
    assert _mode(env_dir) == 0o700
    real = _private_dir.os.getuid()
    monkeypatch.setattr(_private_dir.os, "getuid", lambda: real + 1)
    with pytest.raises(SchemaCacheError, match="owned by another user"):
        load_cached(CLI, "dev", URL, ORIGIN)


def test_reads_are_size_bounded(monkeypatch):
    _write()
    monkeypatch.setattr(cache_mod, "MAX_SCHEMA_BYTES", 10)
    with pytest.raises(SchemaCacheError, match="larger than 10 bytes"):
        load_cached(CLI, "dev", URL, ORIGIN)


def test_unsupported_platform_is_a_cache_error(monkeypatch):
    monkeypatch.setattr(_private_dir, "private_dirs_supported", lambda: False)
    with pytest.raises(SchemaCacheError, match="no secure file store"):
        load_cached(CLI, "dev", URL, ORIGIN)


def test_corrupt_meta_is_refused():
    _write()
    (cache_dir(CLI) / "dev" / "meta.json").write_text('{"origin": 1}')
    with pytest.raises(SchemaCacheError, match="corrupt"):
        _meta()


@pytest.mark.parametrize(
    "body", [b"[]", b"not json", b'{"openapi": "3.1.0"}', b'{"paths": {}}', b"[" * 100000]
)
def test_write_refuses_a_non_openapi_body(body):
    with pytest.raises(SchemaCacheError):
        _write(data=body)
    assert not (cache_dir(CLI) / "dev" / "openapi.json").exists()


def test_touch_keeps_the_schema_and_moves_fetched_at():
    meta = _write(etag="e1")
    old = meta.__class__(
        meta.url, meta.origin, meta.fingerprint, meta.etag, "2020-01-01T00:00:00+00:00"
    )
    with open_cache(CLI, "dev", create=False) as store:
        fresh = touch_in(store, old)
    assert fresh.fingerprint == meta.fingerprint and fresh.fetched_at != old.fetched_at
    assert _meta() == fresh
    assert old.age_seconds() > 86400 and (fresh.age_seconds() or 0) < 60
