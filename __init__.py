from typing import Any, Awaitable, Callable, Optional, TypeVar
import asyncio
import sublime
import threading


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


T = TypeVar("T")


def run_in_main_thread(f: Callable[..., T], *args: Any, **kwargs: Any) -> Awaitable[T]:
    """
    Run a blocking function on the main thread. Return a future that contains the result.

    You use this in a coroutine function like this:

    ```
    def display_something() -> int:
        v = sublime.active_window().active_view()
        v.add_regions("asdf", [])
        return 42

    async def my_coroutine() -> None:
        result = await run_in_main_thread(display_something)
        # result contains 42
    ```
    """
    future = asyncio.get_running_loop().create_future()

    def wrap() -> None:
        result = f(*args, **kwargs)
        get().call_soon_threadsafe(lambda: future.set_result(result))

    sublime.set_timeout(wrap)
    return future


def run_in_worker_thread(f: Callable[..., T], *args: Any, **kwargs: Any) -> Awaitable[T]:
    """
    Run a blocking function on the worker ("async") thread. Return a future that contains the result.

    You use this in a coroutine function like this:

    ```
    def compute_something() -> float:
        return 42.0

    async def my_coroutine() -> None:
        result = await run_in_worker_thread(compute_something)
        # result contains 42.0
    ```
    """
    future = asyncio.get_running_loop().create_future()

    def wrap() -> None:
        result = f(*args, **kwargs)
        get().call_soon_threadsafe(lambda: future.set_result(result))

    sublime.set_timeout_async(wrap)
    return future


async def next_frame() -> None:
    """
    Wait for the next UI frame.
    """
    await run_in_main_thread(lambda: None)
