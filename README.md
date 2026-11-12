# clem

`clem` is a read-only command-line client for downloading reservation data from the [Thoiry Espace Citoyens portal](https://www.espace-citoyens.net/thoiry/espace-citoyens/).

The CLI reads the household account's dashboard and reservation calendar. `get-all-reservations` returns all booked days as JSON; `check-reservation` filters those same cached records by child and date. Progress is written to stderr; JSON or a structured error is written to stdout. The tool does not create, change, or cancel reservations. It is an independent project and is not affiliated with or endorsed by the portal or the municipality.

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- An account for the Thoiry Espace Citoyens portal

## Install

```sh
git clone https://github.com/dberzano/clem.git
cd clem
uv sync
```

Provide portal credentials through `CLEM_USERNAME` and `CLEM_PASSWORD`, or in `~/.config/clem/config.toml`:

```toml
username = "your-portal-username"
password = "your-portal-password"
```

Keep credentials and the cached session private; never commit them.

## Run

Get every reservation as JSON:

```sh
uv run clem get-all-reservations --parallel 4
```

Check one child's reservations for the current Monday–Friday work week:

```sh
uv run clem check-reservation --kid "Child Name"
```

The default date range is Monday through Friday of the current week in `Europe/Paris`. Supply either or both inclusive bounds explicitly; dates use `YYYY-MM-DD`:

```sh
uv run clem check-reservation --kid "Child Name" --start-date 2026-11-09 --end-date 2026-11-13
```

`--format pretty` is the default: Rich tables group days under ISO year/week headings, with a horizontal separator between each day's row. Activities use distinct colors; empty days say `No reservations`. Use `--format json` for the matching records unchanged from the all-reservations data.

Each JSON record includes the child name, activity, place, unit, date, quantity, and whether that day is editable. Treat the output as personal information and avoid sharing or publishing it.

Options `--parallel`, `--force-auth`, and `--force-scan` are available on both commands. `--force-scan` bypasses the two-hour result cache; combine it with `--force-auth` to discard the saved session and log in again.

The session cookie is cached at `~/.cache/clem/session.json`. Successful scans save reservation JSON at `~/.cache/clem/reservations.json`; its modification time determines whether it is still fresh (two hours). A fresh cache hit makes no portal API or login requests and logs its age to stderr. Any fetch or parsing failure aborts the run rather than returning partial results.

## Scope and limitations

This project is tailored to the Thoiry portal's current dashboard and reservation-calendar responses. It reports booked days available through those views; it does not report holiday programs or one-off activities that are absent from the dashboard. Portal markup or API changes may require updates to the parser.
