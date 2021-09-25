"""
Entrypoint for cooperative packages sharing a common global loop.

A minimal plugin looks like this:

```python
from typing import Optional
import sublime_asyncio
import sublime_plugin
import asyncio


async def exit_handler() -> None:
    print("FooAsync: shutting down lots of asynchronous processes...")
    await asyncio.sleep(1.0)
    if _task:
        _task.cancel()
    print("Done shutting down")


async def run() -> None:
    try:
        while True:
            print("Hello from FooAsync coroutine")
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        print("FooAsync got cancelled")


_exit_handler_id = 0
_task: Optional[asyncio.Task] = None


def plugin_loaded() -> None:
    global _exit_handler_id
    _exit_handler_id = sublime_asyncio.acquire(exit_handler)

    def store_task(task: asyncio.Task) -> None:
        global _task
        _task = task

    sublime_asyncio.dispatch(run(), store_task)


def plugin_unloaded() -> None:
    sublime_asyncio.release(at_exit=False, exit_handler_id=_exit_handler_id)


class EventListener(sublime_plugin.EventListener):
    def on_exit(self) -> None:
        print("on_exit was called for FooAsync")
        sublime_asyncio.release(at_exit=True)
```

"""

import asyncio
import threading
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

ExitHandler = Callable[[], Awaitable[None]]
T = TypeVar("T")


class _Data:
    def __init__(self) -> None:
        self.refcount = 1
        self.loop = asyncio.new_event_loop()
        self.exit_handlers: Dict[int, ExitHandler] = {}

    def __del__(self) -> None:
        for task in asyncio.all_tasks(self.loop):
            task.cancel()
        try:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        except Exception as ex:
            print("Exception while shutting down asynchronous generators:", ex)
        self.loop.close()

    def blocking_stop(self) -> None:
        self.loop.call_soon_threadsafe(lambda: asyncio.get_running_loop().stop())
        self.thread.join()

    def start(self) -> None:
        self.thread = threading.Thread(target=self.loop.run_forever)
        self.thread.start()

    def run_all_exit_handlers(self) -> None:
        self.loop.run_until_complete(self._invoke_exit_handlers())

    async def _invoke_exit_handlers(self) -> None:
        coros: List[Awaitable[None]] = []
        for handler in self.exit_handlers.values():
            coros.append(handler())
        for result in await asyncio.gather(*coros, return_exceptions=True):
            if isinstance(result, Exception):
                print("Exception in exit handler:", result)
        self.exit_handlers.clear()


_data = None  # type: Optional[_Data]
_exit_handler_id = 0


def acquire(exit_handler: Optional[ExitHandler] = None) -> Optional[int]:
    """
    MUST be called in your plugin_loaded()

    The optional argument 'exit_handler' is a coroutine function that will be invoked on the main thread during app
    shutdown in EventListener.on_exit. In your exit_handler, you MUST NOT call any Sublime Text API functions. All
    registered exit handlers are ran concurrently.

    When you supply an exit handler, this function returns an integer ID that you MUST pass on to `release`.
    """
    global _data
    global _exit_handler_id
    if _data is None:
        _data = _Data()
        _data.start()
    else:
        _data.refcount += 1
    if exit_handler:
        _exit_handler_id += 1
        _data.exit_handlers[_exit_handler_id] = exit_handler
        return _exit_handler_id
    return None


def release(at_exit: bool, exit_handler_id: Optional[int] = None) -> None:
    """
    This function MUST be called in exactly two places:

    - in your `plugin_unloaded()` callback from ST with at_exit = False, and
    - in your `EventListener.on_exit()` callback from ST with at_exit = True.

    When an exit_handler_id is supplied, this function will stop the loop momentarily, and then run your asynchronous
    exit handler in the main thread. This means the main thread is temporarily blocked.

    When at_exit is True, the exit_handler_id is ignored and instead all registered exit handlers are invoked
    concurrently, but still on the main thread. You MUST NOT call any ST API functions in your exit handler.
    """
    global _data
    if _data is None:
        return
    _data.blocking_stop()
    if at_exit:
        _data.run_all_exit_handlers()
        _data = None
    else:
        if exit_handler_id:
            handler = _data.exit_handlers.pop(exit_handler_id, None)
            if handler:
                try:
                    _data.loop.run_until_complete(handler())
                except Exception as ex:
                    print("Exception in exit handler:", ex)
        _data.refcount -= 1
        if _data.refcount > 0:
            _data.start()
        else:
            _data = None


def get() -> asyncio.AbstractEventLoop:
    """Get access to the loop"""
    global _data
    if not _data:
        raise RuntimeError("get() called before acquire() or after release()")
    return _data.loop


def call_soon_threadsafe(callback: Callable[..., Any], *args: Any) -> None:
    get().call_soon_threadsafe(callback, *args)


def dispatch(coro: Awaitable[Any], task_receiver: Optional[Callable[[asyncio.Task], Any]] = None) -> None:
    """
    Convenience function to run a coroutine.

    This differs from asyncio.run_coroutine_threadsafe in that it doesn't create a threading.Condition for
    every call to this function. Because of this, it is generally unsafe to check whether the future would be done
    or contains an exception. Therefore we don't return a future.

    The second argument is an optional callable that receives the spawned task. You can use it to store the task
    somewhere and then possibly cancel it at a later point in time.

    To get back on Sublime's main thread you use the usual strategy of calling `sublime.set_timeout`. Only this time
    you call it from within your coroutine function.
    """

    def wrap() -> None:
        task = asyncio.get_running_loop().create_task(coro)
        if task_receiver:
            task_receiver(task)

    call_soon_threadsafe(wrap)


def sync(coro: Awaitable[T]) -> T:
    """
    Run an asynchronous function in a blocking manner.
    """
    global _data
    if _data is None:
        raise RuntimeError("sync() called before acquire() or after release()")
    _data.blocking_stop()
    try:
        return _data.loop.run_until_complete(coro)
    finally:
        _data.start()
