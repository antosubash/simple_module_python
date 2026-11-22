"""A bounded event-loop thread for cross-loop backend cleanup tests."""

import asyncio
from contextlib import contextmanager
from threading import Event, Thread

from simple_module_hosting._lease_redis import RedisLeaseBackend


@contextmanager
def running_loop():
    loop = asyncio.new_event_loop()
    ready = Event()
    cleanup_ready = Event()

    async def cancel_pending():
        tasks = asyncio.all_tasks(loop) - {asyncio.current_task()}
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def serve():
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        try:
            loop.run_forever()
        finally:
            assert cleanup_ready.wait(5)
            loop.run_until_complete(cancel_pending())
            loop.close()

    thread = Thread(target=serve, daemon=True)
    thread.start()
    try:
        assert ready.wait(5)
        yield loop
    finally:
        if loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        cleanup_ready.set()
        thread.join(timeout=5)
        assert not thread.is_alive()


class Client:
    def __init__(self):
        self.closed = False
        self.close_count = 0

    async def aclose(self):
        self.close_count += 1
        self.closed = True
        self.closed_loop = asyncio.get_running_loop()

    async def eval(self, *args):
        assert not self.closed
        return 1


def make_backend(first_type=Client):
    clients = []

    def factory():
        client = Client() if clients else first_type()
        clients.append(client)
        return client

    return RedisLeaseBackend("redis://unused", factory=factory), clients
