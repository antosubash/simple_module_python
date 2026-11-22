"""Boot output must not leave stderr locked during interpreter shutdown."""

import os
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX pipe descriptors")
@pytest.mark.parametrize("full_pipe,message_size", [(True, 32), (False, 1024 * 1024)])
def test_interpreter_exits_with_blocking_stderr_pipe(full_pipe, message_size):
    code = textwrap.dedent(
        f"""
        import asyncio
        import os
        from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
        from simple_module_hosting.boot import _dev_boot

        read_fd, write_fd = os.pipe()
        if {full_pipe!r}:
            os.set_blocking(write_fd, False)
            try:
                while True:
                    os.write(write_fd, b'x' * 4096)
            except BlockingIOError:
                pass
            os.set_blocking(write_fd, True)
        os.dup2(write_fd, 2)
        os.close(write_fd)
        # Keep read_fd open, but never drain it, even after boot returns.
        _dev_boot._OUTPUT_TIMEOUT = 0.05
        asyncio.run(_dev_boot.print_boot_diagnostics([
            Diagnostic(DiagnosticLevel.WARNING, 'SM003', 'x' * {message_size}, 'Demo')
        ]))
        assert os.get_blocking(2)
        print('boot returned', flush=True)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=5, check=True
    )
    assert result.stdout == "boot returned\n"
