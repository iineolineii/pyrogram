#  Pyrogram - Telegram MTProto API Client Library for Python
#  Copyright (C) 2017-present Dan <https://github.com/delivrance>
#
#  This file is part of Pyrogram.
#
#  Pyrogram is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Pyrogram is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import functools
import inspect
import threading

from pyrogram import types
from pyrogram.methods import Methods
from pyrogram.methods.utilities import idle as idle_module, compose as compose_module
from pyrogram.utils import get_event_loop


def async_to_sync(obj, name):
    function = getattr(obj, name)
    main_loop = get_event_loop()

    def async_to_sync_gen(agen, loop, is_main_thread):
        async def anext(agen):
            try:
                return await agen.__anext__(), False
            except StopAsyncIteration:
                return None, True

        while True:
            if is_main_thread:
                item, done = loop.run_until_complete(anext(agen))
            else:
                item, done = asyncio.run_coroutine_threadsafe(anext(agen), loop).result()

            if done:
                break

            yield item

    @functools.wraps(function)
    def async_to_sync_wrap(*args, **kwargs):
        coroutine = function(*args, **kwargs)

        try:
            loop = get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if threading.current_thread() is threading.main_thread() or not main_loop.is_running():
            if loop.is_running():
                return coroutine
            else:
                if inspect.iscoroutine(coroutine):
                    return loop.run_until_complete(coroutine)

                if inspect.isasyncgen(coroutine):
                    return async_to_sync_gen(coroutine, loop, True)
        else:
            if inspect.iscoroutine(coroutine):
                if loop.is_running():
                    async def coro_wrapper():
                        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coroutine, main_loop))

                    return coro_wrapper()
                else:
                    return asyncio.run_coroutine_threadsafe(coroutine, main_loop).result()

            if inspect.isasyncgen(coroutine):
                if loop.is_running():
                    return coroutine
                else:
                    return async_to_sync_gen(coroutine, main_loop, False)

    async_to_sync_wrap._orig = function

    setattr(obj, name, async_to_sync_wrap)


def wrap_entity(entity):
    for name in dir(entity):
        method = getattr(entity, name)

        if not name.startswith("_"):
            if inspect.iscoroutinefunction(method) or inspect.isasyncgenfunction(method):
                async_to_sync(entity, name)

def unwrap_entity(entity):
    for name in dir(entity):
        method = getattr(entity, name)

        if not name.startswith("_"):
            if hasattr(method, "_orig"):
                setattr(entity, name, method._orig)


def wrap():
    # Wrap all Client's relevant methods
    wrap_entity(Methods)

    # Wrap types' bound methods
    for class_name in dir(types):
        cls = getattr(types, class_name)

        if inspect.isclass(cls):
            wrap_entity(cls)

    # Special case for idle and compose, because they are not inside Methods
    async_to_sync(idle_module, "idle")

    async_to_sync(compose_module, "compose")


def unwrap():
    unwrap_entity(Methods)

    for class_name in dir(types):
        cls = getattr(types, class_name)

        if inspect.isclass(cls):
            unwrap_entity(cls)

    idle_module.idle = idle_module.idle._orig
    compose_module.compose = compose_module.compose._orig


wrap()

idle = getattr(idle_module, "idle")
compose = getattr(compose_module, "compose")
