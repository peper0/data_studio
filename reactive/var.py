import asyncio
import os
import weakref
from contextlib import suppress
from typing import Any, Awaitable, NamedTuple, List, Callable, Coroutine, Iterable

CoroutineFunction = Callable[[], Coroutine]


def myprint(*args):
    os.write(1, (' '.join(map(str, args))+'\n').encode())


class QueueItem(NamedTuple):
    priority: int
    id: Any
    awaitable: Awaitable

    def __lt__(self, other):
        return self.priority < other.priority


def rethrow(f):
    # print("finished: %s" % f)
    if f.cancelled():
        print("task was canceled")
        return
    e = f.exception()
    if e:
        print("err: ", e.__class__, e)
        myprint("ERROR==================: ", e.__class__, e)
        if isinstance(e, asyncio.CancelledError):
            print("task was canceled 2")
        else:
            raise e


class Refresher:
    def __init__(self):
        self.queue = asyncio.PriorityQueue()
        print("starting")
        self.task = None  # type: asyncio.Task

    def maybe_start_task(self):
        if not self.task or self.task.done():
            self.task = asyncio.ensure_future(self.run())  # type: asyncio.Task
            self.task.add_done_callback(rethrow)

    def add_coroutine(self, hash, coro):
        t = QueueItem(1, hash, coro)
        self.queue.put_nowait(t)
        self.maybe_start_task()

    async def run(self):
        update_next = None

        with suppress(asyncio.QueueEmpty):  # it's ok - if the queue is empty we just exit
            while True:
                update = update_next if update_next else self.queue.get_nowait()
                try:
                    update_next = self.queue.get_nowait()
                    if update_next.id == update.id:  # skip update if is same as next
                        continue
                except asyncio.QueueEmpty:
                    update_next = None

                try:
                    await update.awaitable
                except Exception as e:
                    myprint("ERROR in some handler ==================: ", e.__class__, e)


refresher = None


async def wait_for_var(var):
    # fixme: waiting only for certain level
    await refresher.task


def get_default_refresher():
    global refresher
    if not refresher:
        refresher = Refresher()

    return refresher


class Var:
    def __init__(self, data=None):
        self.data = data
        self._observers = weakref.WeakSet()  # Iterable[CoroutineFunction]
        #self._observers = set()  # Iterable[CoroutineFunction]
        self.on_dispose = None
        self.disposed = False
        self._kept_references = []

    def __del__(self):
        print("deleting", self, self.disposed, self.on_dispose)
        if not self.disposed and self.on_dispose:
            os.write(1, b"will dispose\n")
            get_default_refresher().add_coroutine(self.on_dispose, self.on_dispose())
            # assert self.disposed, "Var.dispose was not called before destroying"

    def set(self, new_data):
        self.data = new_data
        for corof in self._observers:   # type: CoroutineFunction
            get_default_refresher().add_coroutine(corof, corof())

    async def dispose(self):
        if not self.disposed:
            print("disposing?")
            if self.on_dispose:
                print("disposing")
                await self.on_dispose()
            self.disposed = True
            # def __getattr__(self, item):
            #    print("getattr %s"% item)
            # def __getattribute__(self, item):
            #    print("getattribute %s"% item)

            # @reactive
            # def __add__(x, y):
            #    return x + y

    def add_observer(self, observer: CoroutineFunction):
        myprint("added observer", observer, 'to', self)
        self._observers.add(observer)

    def keep_reference(self, o):
        """
        Keeps a reference to `o` for own Var instance lifetime.
        """
        self._kept_references.append(o)

