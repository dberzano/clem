import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

import typer
from pydantic import TypeAdapter, ValidationError
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from .client import Client
from .config import RESULT_CACHE_PATH, RESULT_CACHE_TTL_SECONDS, RESERVATION_TIMEZONE
from .errors import ClemError
from .models import ErrorDetail, ErrorOutput, Reservation
from .progress import Reporter, RichReporter
from .reservations import fetch_reservations

app = typer.Typer(add_completion=False, no_args_is_help=True)
_RESERVATIONS = TypeAdapter(list[Reservation])
logger = logging.getLogger(__name__)

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_ACTIVITY_COLORS = (
    "cyan",
    "green",
    "magenta",
    "yellow",
    "blue",
    "red",
    "bright_cyan",
    "bright_green",
    "bright_magenta",
    "bright_blue",
    "bright_red",
    "bright_yellow",
)


class ReservationFormat(str, Enum):
    JSON = "json"
    PRETTY = "pretty"


def _format_age(age_seconds: float) -> str:
    seconds = int(age_seconds)
    hours, seconds = divmod(seconds, 60 * 60)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    for value, unit in ((hours, "hour"), (minutes, "minute"), (seconds, "second")):
        if value:
            parts.append(f"{value} {unit}{'' if value == 1 else 's'}")
    return ", ".join(parts) or "0 seconds"


def _log_cache_age(age_seconds: float) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        logger.info("Returning cached data from %s ago.", _format_age(age_seconds))
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


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


def _get_all_reservations(parallel: int, force_auth: bool, force_scan: bool) -> list[Reservation]:
    cached = _read_cache(force_scan)
    if cached is not None:
        reservations, age = cached
        _log_cache_age(age)
        return reservations

    reporter = RichReporter() if sys.stderr.isatty() else Reporter()
    try:
        with reporter, Client(reporter=reporter) as client:
            if force_auth:
                client.clear_session()
            reservations = fetch_reservations(client, parallel, reporter)
    except ClemError as e:
        print(ErrorOutput(error=ErrorDetail(code=e.code, message=e.message)).model_dump_json())
        raise typer.Exit(code=e.exit_code)

    try:
        _write_cache(reservations)
    except OSError as e:
        logger.warning("Could not save reservation cache: %s", e)
    return reservations


def _resolve_date_range(start_date: Optional[date], end_date: Optional[date]) -> tuple[date, date]:
    today = datetime.now(RESERVATION_TIMEZONE).date()
    monday = today - timedelta(days=today.weekday())
    start = start_date if start_date is not None else monday
    end = end_date if end_date is not None else monday + timedelta(days=4)
    if start > end:
        raise typer.BadParameter("start date must be on or before end date")
    return start, end


def _filter_reservations(
    reservations: list[Reservation], kid: str, start_date: date, end_date: date
) -> list[Reservation]:
    kid_key = kid.casefold()
    return [
        reservation
        for reservation in reservations
        if reservation.kid_name.casefold() == kid_key
        and start_date <= reservation.date <= end_date
    ]


def _print_pretty(reservations: list[Reservation], start_date: date, end_date: date) -> None:
    by_date: dict[date, list[Reservation]] = {}
    for reservation in reservations:
        by_date.setdefault(reservation.date, []).append(reservation)

    console = Console(file=sys.stdout, highlight=False, no_color=False)
    activity_colors: dict[str, str] = {}
    current = start_date
    current_week = None
    table: Table | None = None
    while current <= end_date:
        iso_date = current.isocalendar()
        week = (iso_date.year, iso_date.week)
        if week != current_week:
            if table is not None:
                console.print(table)
            table = Table(
                title=Text(
                    f"{iso_date.year} · Week {iso_date.week:02d}",
                    style="bold cyan",
                ),
                box=box.ROUNDED,
                header_style="bold",
                padding=(0, 1),
            )
            table.add_column("Day", style="bold", no_wrap=True)
            table.add_column("Reservations", overflow="fold")
            current_week = week

        label = f"{_WEEKDAYS[current.weekday()]} {_MONTHS[current.month - 1]} {current.day}"
        day_reservations = by_date.get(current, [])
        if day_reservations:
            activities = Text()
            for index, item in enumerate(day_reservations):
                if index:
                    activities.append("\n")
                color = activity_colors.get(item.activity)
                if color is None:
                    color = _ACTIVITY_COLORS[len(activity_colors) % len(_ACTIVITY_COLORS)]
                    activity_colors[item.activity] = color
                style = f"bold {color}"
                activities.append("• ", style=style)
                activities.append(item.activity, style=style)
            table.add_row(Text(label, style="cyan"), activities)
        else:
            table.add_row(
                Text(label, style="cyan"),
                Text("No reservations", style="dim italic"),
            )
        current += timedelta(days=1)

    if table is not None:
        console.print(table)


@app.command("get-all-reservations")
def get_all_reservations(
    parallel: int = typer.Option(6, "--parallel", min=1, help="Worker threads for fetching."),
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
    """Return all household reservations as JSON."""
    reservations = _get_all_reservations(parallel, force_auth, force_scan)
    print(_RESERVATIONS.dump_json(reservations).decode())


@app.command("check-reservation")
def check_reservation(
    kid: str = typer.Option(..., "--kid", help="Kid's name (case-insensitive)."),
    start_date: Optional[date] = typer.Option(None, "--start-date", help="First date, inclusive (YYYY-MM-DD)."),
    end_date: Optional[date] = typer.Option(None, "--end-date", help="Last date, inclusive (YYYY-MM-DD)."),
    output_format: ReservationFormat = typer.Option(
        ReservationFormat.PRETTY,
        "--format",
        help="Output as the original JSON subset or a weekly summary.",
    ),
    parallel: int = typer.Option(6, "--parallel", min=1, help="Worker threads for fetching."),
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
    """Check one kid's reservations within an inclusive date range."""
    start, end = _resolve_date_range(start_date, end_date)
    reservations = _get_all_reservations(parallel, force_auth, force_scan)
    matches = _filter_reservations(reservations, kid, start, end)
    if output_format is ReservationFormat.JSON:
        print(_RESERVATIONS.dump_json(matches).decode())
    else:
        _print_pretty(matches, start, end)
