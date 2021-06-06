import asyncio
from asyncio.tasks import Task
from typing import Any, Awaitable
from weakref import WeakSet
import threading

import sublime
import sublime_plugin

from .globalstate import call_soon_threadsafe, run_coroutine


class DispatchMixin:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        print("DispatchMixin", self, "__init__")
        self.__tasks_lock = threading.Lock()
        self.__tasks = WeakSet()  # type: WeakSet[Task]

    def __del__(self) -> None:
        print("DispatchMixin", self, "__del__")
        with self.__tasks_lock:
            tasks = list(self.__tasks)
            self.__tasks.clear()
        print("attempting to cancel these tasks:", tasks)
        if tasks:

            def wrap() -> None:
                for task in tasks:
                    if task:
                        task.cancel()

            call_soon_threadsafe(wrap)

    def dispatch(self, awaitable: Awaitable[Any]) -> bool:

        async def wrap() -> None:
            task = asyncio.ensure_future(awaitable)
            with self.__tasks_lock:
                self.__tasks.add(task)
                print("after addition, stored tasks:", self.__tasks)
            try:
                await awaitable
            finally:
                with self.__tasks_lock:
                    self.__tasks.discard(task)
                    print("after removal, stored tasks:", self.__tasks)

        return run_coroutine(wrap())


class ApplicationCommand(sublime_plugin.ApplicationCommand, DispatchMixin):
    """
    An asynchronous ApplicationCommand. Define the `execute` method instead
    of the `run` method.
    """

    def run(self, **kwargs: Any) -> None:
        self.dispatch(self.execute(**kwargs))  # type: ignore


class WindowCommand(sublime_plugin.WindowCommand, DispatchMixin):
    """
    An asynchronous WindowCommand. Define the `execute` method instead
    of the `run` method.
    """

    def __init__(self, window: sublime.Window):
        super().__init__(window)
        DispatchMixin.__init__(self)

    def run(self, **kwargs: Any) -> None:
        self.dispatch(self.execute(**kwargs))  # type: ignore


class ViewCommand(sublime_plugin.TextCommand, DispatchMixin):
    """
    An asynchronous ViewCommand. Define the `execute` method instead
    of the `run` method.
    """

    def __init__(self, view: sublime.View):
        super().__init__(view)
        DispatchMixin.__init__(self)

    def run(self, _: sublime.Edit, **kwargs: Any) -> None:  # type: ignore
        self.dispatch(self.execute(**kwargs))  # type: ignore
