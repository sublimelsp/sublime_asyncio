"""
This module bridges the old, low-level callback-based functions to high-level async functions.
"""
import asyncio
import functools
from typing import Any, Awaitable, Callable, Optional, Sequence, Tuple, TypeVar, Union

import sublime

from sublime_asyncio.globalstate import call_soon_threadsafe

T = TypeVar("T")


def _resolve_function_invocation(future: asyncio.Future, f: Callable[..., T], *args: Any, **kwargs: Any) -> None:
    try:
        call_soon_threadsafe(future.set_result, f(*args, **kwargs))
    except Exception as ex:
        call_soon_threadsafe(future.set_exception, ex)


def _run_in_runner(
    runner: Callable[[Callable[[], None]], None], f: Callable[..., T], *args: Any, **kwargs: Any
) -> Awaitable[T]:
    future = asyncio.get_running_loop().create_future()
    runner(functools.partial(_resolve_function_invocation, future, f, *args, **kwargs))
    return future


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
    return _run_in_runner(sublime.set_timeout, f, *args, **kwargs)


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
    return _run_in_runner(sublime.set_timeout_async, f, *args, **kwargs)


async def next_frame() -> None:
    """
    Wait for the next UI frame.
    """
    await run_in_main_thread(lambda: None)


def get_clipboard(size_limit: int = 16777216) -> Awaitable[str]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        sublime.get_clipboard_async(
            lambda content: call_soon_threadsafe(
                lambda: future.set_result(content)),
            size_limit=size_limit)
    except Exception as ex:
        future.set_exception(ex)
    return future


def open_dialog(
    file_types: Sequence[Tuple[str, Sequence[str]]] = [],
    directory: Optional[str] = None,
    multi_select: bool = False,
    allow_folders: bool = False,
) -> Awaitable[str]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        sublime.open_dialog(
            callback=functools.partial(_resolve_optional_string, future),
            file_types=file_types,
            directory=directory,
            multi_select=multi_select,
            allow_folders=allow_folders,
        )
    except Exception as ex:
        future.set_exception(ex)
    return future


def save_dialog(
    file_types: Sequence[Tuple[str, Sequence[str]]] = [],
    directory: Optional[str] = None,
    name: Optional[str] = None,
    extension: Optional[str] = None,
) -> Awaitable[str]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        sublime.save_dialog(
            callback=functools.partial(_resolve_optional_string, future),
            file_types=file_types,
            directory=directory,
            name=name,
            extension=extension,
        )
    except Exception as ex:
        future.set_exception(ex)
    return future


def select_folder_dialog(directory: Optional[str] = None, multi_select: bool = False) -> Awaitable[str]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        sublime.select_folder_dialog(
            callback=functools.partial(_resolve_optional_string, future), directory=directory, multi_select=multi_select
        )
    except Exception as ex:
        future.set_exception(ex)
    return future


def show_popup_menu(view: sublime.View, items: Sequence[str], flags: int = 0) -> Awaitable[int]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        view.show_popup_menu(items=items, on_select=lambda index: _resolve_index_selection(future, index), flags=flags)
    except Exception as ex:
        future.set_exception(ex)
    return future


def show_input_panel(
    window: sublime.Window,
    caption: Optional[str] = None,
    initial_text: Optional[str] = None,
    on_change: Optional[Callable[[str], Any]] = None,
) -> Awaitable[str]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        window.show_input_panel(
            caption=caption,
            initial_text=initial_text,
            on_done=lambda s: call_soon_threadsafe(lambda: future.set_result(s)),
            on_change=on_change,
            on_cancel=lambda: call_soon_threadsafe(lambda: future.set_exception(asyncio.CancelledError())),
        )
    except Exception as ex:
        future.set_exception(ex)
    return future


def show_quick_panel(
    window: sublime.Window,
    items: Union[Sequence[str], Sequence[Sequence[str]], Sequence[sublime.QuickPanelItem]],
    flags: int = 0,
    selected_index: int = -1,
    on_highlighted: Optional[Callable[[int], Any]] = None,
    placeholder: Optional[str] = None,
) -> Awaitable[int]:
    """
    See https://www.sublimetext.com/docs/api_reference.html
    """
    future = asyncio.get_running_loop().create_future()
    try:
        window.show_quick_panel(
            items=items,
            on_select=functools.partial(_resolve_index_selection, future),
            flags=flags,
            selected_index=selected_index,
            on_highlight=on_highlighted,
            placeholder=placeholder,
        )
    except Exception as ex:
        future.set_exception(ex)
    return future


def _resolve_optional_string(future: asyncio.Future, s: Optional[str]) -> None:
    if s is None:
        call_soon_threadsafe(future.set_exception, asyncio.CancelledError())
    else:
        call_soon_threadsafe(future.set_result, s)


def _resolve_index_selection(future: asyncio.Future, index: int) -> None:
    if index == -1:
        call_soon_threadsafe(future.set_exception, asyncio.CancelledError())
    else:
        call_soon_threadsafe(future.set_result, index)
