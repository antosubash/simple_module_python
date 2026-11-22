"""A bounded event-loop thread for cross-loop backend cleanup tests."""

import asyncio
from contextlib import contextmanager
from threading import Event, Thread


@contextmanager
def running_loop():
    loop = asyncio.new_event_loop()
    ready = Event()

    def serve():
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert ready.wait(5)
        yield loop
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        if not thread.is_alive():
            loop.close()
