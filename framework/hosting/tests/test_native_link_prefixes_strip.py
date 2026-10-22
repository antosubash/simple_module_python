import pytest
from pydantic import ValidationError
from simple_module_hosting.host_settings import HostSettings


def test_native_prefixes_are_stripped_before_validation():
    s = HostSettings(native_link_prefixes=[" /x", "/y "])
    assert s.native_link_prefixes == ["/x", "/y"]


def test_native_prefix_without_slash_still_rejected():
    with pytest.raises(ValidationError):
        HostSettings(native_link_prefixes=["x"])
