"""Optional task integration must load after its provider when installed."""

from background_tasks.module import BackgroundTasksModule
from file_storage.module import FileStorageModule
from simple_module_core.discovery import topological_sort


def test_background_tasks_loads_before_file_storage():
    storage = FileStorageModule()
    tasks = BackgroundTasksModule()
    assert tasks.meta.name in storage.meta.optional_depends_on
    assert topological_sort([storage, tasks]) == [tasks, storage]
