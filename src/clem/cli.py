import sys

import typer
from pydantic import TypeAdapter

from .client import Client
from .errors import ClemError
from .models import ErrorDetail, ErrorOutput, Reservation
from .progress import Reporter, RichReporter
from .reservations import fetch_reservations

app = typer.Typer(add_completion=False)
_RESERVATIONS = TypeAdapter(list[Reservation])


@app.command()
def main(
    parallel: int = typer.Option(6, "--parallel", min=1, help="Worker threads for fetching."),
    force_auth: bool = typer.Option(False, "--force-auth", help="Ignore the cached session and log in again."),
):
    """All reservations of all kids of the household, as JSON on stdout (progress on stderr)."""
    reporter = RichReporter() if sys.stderr.isatty() else Reporter()
    try:
        with reporter, Client(reporter=reporter) as client:
            if force_auth:
                client.clear_session()
            reservations = fetch_reservations(client, parallel, reporter)
        print(_RESERVATIONS.dump_json(reservations).decode())
    except ClemError as e:
        print(ErrorOutput(error=ErrorDetail(code=e.code, message=e.message)).model_dump_json())
        sys.exit(e.exit_code)
