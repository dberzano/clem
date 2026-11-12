"""Progress reporting on stderr.

Overall bar 0-100 % by stage:
    0-5   load dashboard      5-10  log in (skipped when the cookie is valid)
    10-15 parse dashboard     15-95 fetch registrations (2 steps each, equal weight)
    95-100 merge
Each active worker thread also gets its own transient line under the bar.
"""
import threading

from rich.console import Console, Group
from rich.live import Live
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.text import Text

FETCH_START = 15.0
FETCH_END = 95.0


class Reporter:
    """No-op reporter, used when stderr is not a terminal."""

    def __enter__(self) -> "Reporter":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def status(self, text: str, percent: float) -> None: ...
    def describe(self, text: str) -> None: ...
    def begin_fetch(self, total_steps: int) -> None: ...
    def advance(self) -> None: ...
    def worker_started(self, key: int, label: str) -> None: ...
    def worker_step(self, key: int, text: str) -> None: ...
    def worker_done(self, key: int) -> None: ...


class RichReporter(Reporter):
    """Overall bar on top, one dim '· label: step' line per active worker below it."""

    def __init__(self) -> None:
        console = Console(stderr=True)
        self._lock = threading.Lock()
        self._rows: dict[int, str] = {}
        self._labels: dict[int, str] = {}
        self._overall = 0
        self._step = 0.0
        self._progress = Progress(
            BarColumn(), TaskProgressColumn(), TextColumn("{task.description}"), console=console,
        )
        self._live = Live(get_renderable=self._render, console=console, transient=True,
                          refresh_per_second=10)

    def _render(self) -> Group:
        with self._lock:
            rows = list(self._rows.values())
        return Group(self._progress, *(Text(f"· {row}", style="dim") for row in rows))

    def __enter__(self) -> "RichReporter":
        self._overall = self._progress.add_task("", total=100)
        self._live.start()
        return self

    def __exit__(self, *exc) -> None:
        self._live.stop()

    def status(self, text: str, percent: float) -> None:
        self._progress.update(self._overall, description=text, completed=percent)

    def describe(self, text: str) -> None:
        self._progress.update(self._overall, description=text)

    def begin_fetch(self, total_steps: int) -> None:
        self._step = (FETCH_END - FETCH_START) / total_steps

    def advance(self) -> None:
        self._progress.advance(self._overall, self._step)

    def worker_started(self, key: int, label: str) -> None:
        with self._lock:
            self._labels[key] = label
            self._rows[key] = f"{label}: loading page"

    def worker_step(self, key: int, text: str) -> None:
        with self._lock:
            self._rows[key] = f"{self._labels[key]}: {text}"

    def worker_done(self, key: int) -> None:
        with self._lock:
            self._rows.pop(key, None)
            self._labels.pop(key, None)
