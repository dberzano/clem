import logging
import os
import sys
import time

import typer
from pydantic import TypeAdapter, ValidationError

from .client import Client
from .config import RESULT_CACHE_PATH, RESULT_CACHE_TTL_SECONDS
from .errors import ClemError
from .models import ErrorDetail, ErrorOutput, Reservation
from .progress import Reporter, RichReporter
from .reservations import fetch_reservations

app = typer.Typer(add_completion=False)
_RESERVATIONS = TypeAdapter(list[Reservation])
logger = logging.getLogger(__name__)


def _format_age(age_seconds: float) -> str:
    seconds = int(age_seconds)
    hours, seconds = divmod(seconds, 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    for value, unit in ((hours, "hour"), (minutes, "minute"), (seconds, "second")):
        if value:
            parts.append(f"{value} {unit}{'' if value == 1 else 's'}")
    return ", ".join(parts) or "0 seconds"


def _read_cache(force_scan: bool) -> tuple[list[Reservation], float] | None:
    if force_scan:
        return None
    try:
        age = max(0.0, time.time() - RESULT_CACHE_PATH.stat().st_mtime)
        if age >= RESULT_CACHE_TTL_SECONDS:
            return None
        reservations = _RESERVATIONS.validate_json(RESULT_CACHE_PATH.read_bytes())
    except (OSError, ValidationError):
        return None
    return reservations, age


def _write_cache(reservations: list[Reservation]) -> None:
    RESULT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(RESULT_CACHE_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as cache_file:
        os.fchmod(cache_file.fileno(), 0o600)
        cache_file.write(_RESERVATIONS.dump_json(reservations))


@app.command()
def main(
    parallel: int = typer.Option(
        6,
        "--parallel",
        min=1,
        help="Worker threads for fetching.",
    ),
    force_auth: bool = typer.Option(
        False,
        "--force-auth",
        help="Ignore the cached session and log in again during a scan.",
    ),
    force_scan: bool = typer.Option(
        False,
        "--force-scan",
        help="Ignore cached reservations and fetch fresh data.",
    ),
):
    """All reservations of all kids of the household, as JSON on stdout (progress on stderr)."""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    cached = _read_cache(force_scan)
    if cached is not None:
        reservations, age = cached
        logger.info("Returning cached data from %s ago.", _format_age(age))
        print(_RESERVATIONS.dump_json(reservations).decode())
        return

    reporter = RichReporter() if sys.stderr.isatty() else Reporter()
    try:
        with reporter, Client(reporter=reporter) as client:
            if force_auth:
                client.clear_session()
            reservations = fetch_reservations(client, parallel, reporter)
        try:
            _write_cache(reservations)
        except OSError as e:
            logger.warning("Could not save reservation cache: %s", e)
        print(_RESERVATIONS.dump_json(reservations).decode())
    except ClemError as e:
        print(ErrorOutput(error=ErrorDetail(code=e.code, message=e.message)).model_dump_json())
        sys.exit(e.exit_code)
