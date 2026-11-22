"""An optional consumer registers policies with file_storage uninstalled (#999)."""

import subprocess
import sys


def test_registration_does_not_import_file_storage():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from importlib.abc import MetaPathFinder
from types import SimpleNamespace

class NoStorage(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == 'file_storage' or fullname.startswith('file_storage.'):
            raise ImportError('file_storage is not installed')

sys.meta_path.insert(0, NoStorage())
from simple_module_core.access.file_access import register_file_access_policy, file_access_policies
from simple_module_core.modules.module import ModuleBase, ModuleMeta

class Policy:
    def filter(self, principal, action, stmt): return stmt
    def can(self, principal, action, obj): return False

class Consumer(ModuleBase):
    meta = ModuleMeta(name='Guides', optional_depends_on=['FileStorage'])
    def register_settings(self, app):
        register_file_access_policy(app, 'guides.licence', Policy(), publishable=False)

app = SimpleNamespace(state=SimpleNamespace())
Consumer().register_settings(app)
assert file_access_policies(app).get('guides.licence').publishable is False
assert 'file_storage' not in sys.modules
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
