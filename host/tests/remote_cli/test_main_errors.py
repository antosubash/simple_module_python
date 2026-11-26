"""``smdev`` reports an unusable bundled schema as a clean error."""

import pytest
import smdev_cli


@pytest.mark.parametrize("content", ["{not json", "[]"])
def test_broken_bundled_schema_is_clean_error(tmp_path, monkeypatch, capsys, content):
    broken = tmp_path / "openapi.json"
    broken.write_text(content)
    monkeypatch.setattr(smdev_cli, "SCHEMA_PATH", broken)
    with pytest.raises(SystemExit) as exit_info:
        smdev_cli.main()
    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert "cannot load the bundled command schema" in err


def test_colliding_schema_is_clean_error(tmp_path, monkeypatch, capsys):
    schema = tmp_path / "openapi.json"
    schema.write_text(
        '{"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "paths": {'
        '"/api/a": {"get": {"tags": ["G"], "operationId": "same", "x-sm-token": true}},'
        '"/api/b": {"get": {"tags": ["G"], "operationId": "same", "x-sm-token": true}}}}'
    )
    monkeypatch.setattr(smdev_cli, "SCHEMA_PATH", schema)
    with pytest.raises(SystemExit) as exit_info:
        smdev_cli.main()
    assert exit_info.value.code == 1
    assert "collisions" in capsys.readouterr().err
