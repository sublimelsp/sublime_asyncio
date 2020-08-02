import asyncio
import sublime
import threading
from typing import Awaitable, Optional


class _Thread(threading.Thread):

    def __init__(self) -> None:
        super().__init__()
        self.refcount = 1
        self.loop = asyncio.new_event_loop()

    def run(self) -> None:
        self.loop.run_forever()


_thread = None  # type: Optional[_Thread]


def acquire() -> None:
    """MUST be called in your plugin_loaded()"""
    global _thread
    if _thread is None:
        _thread = _Thread()
        _thread.start()
    else:
        _thread.refcount += 1


def _shutdown() -> None:
    for task in asyncio.Task.all_tasks():
        task.cancel()
    asyncio.get_running_loop().stop()


def release() -> None:
    """MUST be called in your plugin_unloaded()"""
    global _thread
    assert _thread is not None
    _thread.refcount -= 1
    if _thread.refcount == 0:
        _thread.loop.call_soon_threadsafe(_shutdown)
        _thread.join()
        _thread.loop.run_until_complete(_thread.loop.shutdown_asyncgens())
        _thread.loop.close()
        _thread = None


def get() -> asyncio.AbstractEventLoop:
    """Get access to the loop"""
    global _thread
    assert _thread is not None
    return _thread.loop


def run_coroutine(coro: Awaitable) -> None:
    """
    Convenience function to run a coroutine.

    This differs from asyncio.run_coroutine_threadsafe in that it doesn't create a threading.Condition for
    every call to this function. Because of this, it is generally unsafe to check whether the future would be done
    or contains an exception. Therefore we don't return a future.

    To get back on Sublime's main thread you use the usual strategy of calling `sublime.set_timeout`. Only this time
    you call it from within your coroutine function.
    """
    get().call_soon_threadsafe(lambda: asyncio.get_running_loop().create_task(coro))
