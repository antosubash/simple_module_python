"""The bundled ``smdev`` schema passes the shape checks a live schema must pass."""

import json

from simple_module_remote.generate.validate import schema_problems
from smdev_cli import SCHEMA_PATH


def test_bundled_schema_has_no_shape_problems():
    assert schema_problems(json.loads(SCHEMA_PATH.read_text())) == []
