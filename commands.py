import asyncio
from asyncio.tasks import Task
from typing import Any, Awaitable, Generator, List, Optional
from weakref import WeakSet, ref

import sublime
import sublime_plugin

from .globalstate import call_soon_threadsafe, run_coroutine
import contextlib


@contextlib.contextmanager
def stored_task(self: "DispatchMixin") -> Generator[None, None, None]:
    self.__tasks.add(asyncio.current_task())
    yield
    self.__tasks.discard(asyncio.current_task())


class DispatchMixin:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.__tasks = WeakSet()  # type: WeakSet[Optional[Task]]

    def __del__(self) -> None:
        tasks = list(self.__tasks)

        def wrap() -> None:
            for task in tasks:
                if task:
                    task.cancel()

        call_soon_threadsafe(wrap)

    def _store_task(self, task: Task) -> None:
        self.__tasks.add(task)

    def dispatch(self, coro: Awaitable[Any]) -> None:
        async def wrap() -> None:
            with stored_task():
                await coro

        run_coroutine(wrap())



class ApplicationCommand(sublime_plugin.ApplicationCommand, DispatchMixin):
    """
    An asynchronous ApplicationCommand. Override the `execute` method instead
    of the `run` method.
    """
    def run(self, **kwargs: Any) -> None:  # type: ignore
        self.dispatch(self.execute(**kwargs))

    async def execute(self, **kwargs: Any) -> None:
        """
        The asynchronous entrypoint of your command.
        """
        pass


class WindowCommand(sublime_plugin.WindowCommand, DispatchMixin):
    """
    An asynchronous WindowCommand. Override the `execute` method instead
    of the `run` method.
    """
    def __init__(self, window: sublime.Window):
        super().__init__(window)
        DispatchMixin.__init__(self)

    def run(self, **kwargs: Any) -> None:  # type: ignore
        self.dispatch(self.execute(**kwargs))

    async def execute(self, **kwargs: Any) -> None:
        """
        The asynchronous entrypoint of your command.
        """
        pass


class ViewCommand(sublime_plugin.TextCommand, DispatchMixin):
    """
    An asynchronous ViewCommand. Override the `execute` method instead
    of the `run` method.

    This is the concurrent task variant. Meaning, if you run this command, and
    then run it again, the first invocation will keep running.
    """
    def __init__(self, view: sublime.View):
        super().__init__(view)
        DispatchMixin.__init__(self)

    def run(self, _: sublime.Edit, **kwargs: Any) -> None:  # type: ignore
        self.dispatch(self.execute(**kwargs))

    async def execute(self, **kwargs: Any) -> None:
        """
        The asynchronous entrypoint of your command.
        """
        pass
