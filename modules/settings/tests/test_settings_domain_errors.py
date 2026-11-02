"""Settings business failures share a transport-independent base."""


def test_settings_errors_share_a_module_base():
    from settings._managed_keys import ManagedKeyError
    from settings._unique_write import DuplicateSettingError
    from settings.exceptions import SettingsError

    assert isinstance(ManagedKeyError("key", "/clear"), SettingsError)
    assert isinstance(DuplicateSettingError("key"), SettingsError)
