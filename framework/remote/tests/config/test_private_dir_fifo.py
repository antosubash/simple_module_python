"""Reading a FIFO must be refused promptly, not block waiting for a writer."""

import os
import signal
from pathlib import Path

import pytest
from simple_module_remote.config._private_dir import PrivateDir, PrivateDirError

pytestmark = pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs os.mkfifo")


def test_fifo_is_refused_without_blocking(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir(mode=0o700)
    (base / "d").mkdir(mode=0o700)
    os.mkfifo(base / "d" / "creds")
    if hasattr(signal, "SIGALRM"):
        signal.alarm(5)  # a blocking open would hang the suite; fail it instead
    try:
        with PrivateDir(base, "d", create=False) as store, pytest.raises(PrivateDirError) as err:
            store.read("creds", 1024)
    finally:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    assert "not a regular file" in str(err.value)
