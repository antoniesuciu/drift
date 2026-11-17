"""How jobs share the machine. Results never depend on which executor ran them.

NautilusTrader 1.231.0 forbids concurrent engines in one process (global singletons), so
concurrency here means one spawned OS process per job. A dedicated process rather than a pool:
a pool breaks as a whole when one worker dies, and that must cost only that job. `spawn`, not
`fork`, because the engine's runtime threads do not survive a fork.
"""

import multiprocessing
import os
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from multiprocessing.connection import Connection, wait
from multiprocessing.process import BaseProcess
from typing import Any

from drift.data.model import DataError
from drift.research.runner import RunJob, RunOutcome, attempt, failed

_MAX_DEFAULT_WORKERS = 4  # measured 1.3 GB per worker on a 3-year window; 16 GB laptop target


def default_workers(jobs: int) -> int:
    return max(1, min(jobs, (os.cpu_count() or 2) - 1, _MAX_DEFAULT_WORKERS))


@dataclass(frozen=True, slots=True)
class SequentialExecutor:
    """In this process, one at a time: for debuggers and deterministic step-through."""

    @property
    def workers(self) -> int:
        return 1

    def run(self, jobs: Sequence[RunJob], report: Callable[[int, RunOutcome], None]) -> None:
        for index, job in enumerate(jobs):
            report(index, attempt(job))


def _child(writer: Connection, job: RunJob) -> None:
    writer.send(attempt(job))
    writer.close()


@dataclass(slots=True)
class _Live:
    job: RunJob
    process: BaseProcess
    reader: Connection
    started: float


def _collect(live: _Live) -> RunOutcome | None:
    """The job's outcome if it has one yet; None while it is still running."""
    seconds = time.monotonic() - live.started
    alive = live.process.is_alive()  # first: a process seen dead has finished writing
    if live.reader.poll():
        try:
            outcome: RunOutcome = live.reader.recv()
            return outcome
        except (EOFError, OSError):
            pass  # the pipe closed with nothing in it: the process died
    if alive:
        return None
    live.process.join()
    return failed(live.job, "WorkerDied", f"exit code {live.process.exitcode}", seconds)


@dataclass(frozen=True, slots=True)
class ProcessExecutor:
    """At most `workers` jobs at once, each in its own process, each optionally time-limited."""

    workers: int
    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.workers < 1 or (self.timeout_seconds is not None and self.timeout_seconds <= 0):
            raise DataError("workers and timeout must be positive")

    def run(self, jobs: Sequence[RunJob], report: Callable[[int, RunOutcome], None]) -> None:
        context = multiprocessing.get_context("spawn")
        waiting = deque(enumerate(jobs))
        live: dict[int, _Live] = {}
        try:
            while waiting or live:
                while waiting and len(live) < self.workers:
                    index, job = waiting.popleft()
                    reader, writer = context.Pipe(duplex=False)
                    process = context.Process(target=_child, args=(writer, job), daemon=True)
                    process.start()
                    writer.close()  # so the reader sees EOF if the child dies
                    live[index] = _Live(job, process, reader, time.monotonic())
                handles: list[Any] = [w.reader for w in live.values()]
                handles += [w.process.sentinel for w in live.values()]
                wait(handles, timeout=1.0)
                for index, worker in list(live.items()):
                    outcome = _collect(worker)
                    if outcome is None and self._expired(worker):
                        self._stop(worker)
                        seconds = time.monotonic() - worker.started
                        outcome = failed(worker.job, "Timeout", "time limit reached", seconds)
                    if outcome is not None:
                        worker.process.join()
                        worker.reader.close()
                        report(index, outcome)
                        del live[index]
        finally:
            for worker in live.values():
                self._stop(worker)

    def _expired(self, worker: _Live) -> bool:
        limit = self.timeout_seconds
        return limit is not None and time.monotonic() - worker.started > limit

    @staticmethod
    def _stop(worker: _Live) -> None:
        worker.process.terminate()
        worker.process.join(5)
        if worker.process.is_alive():
            worker.process.kill()
            worker.process.join()
