# clem

`clem` is a read-only command-line client for downloading reservation data from the [Thoiry Espace Citoyens portal](https://www.espace-citoyens.net/thoiry/espace-citoyens/).

It logs into the household account, reads the dashboard registrations, and returns booked days for all children and registrations as a JSON array. Progress is written to stderr; JSON or a structured error is written to stdout. The tool does not create, change, or cancel reservations. It is an independent project and is not affiliated with or endorsed by the portal or the municipality.

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

Fetch reservations with four worker threads:

```sh
uv run clem --parallel 4
```

The command prints the reservation list as JSON. Each item includes the child name, activity, place, unit, date, quantity, and whether that day is editable. Treat the output as personal information and avoid sharing or publishing it.

Options:

- `--parallel N`: number of worker threads (default: `6`; minimum: `1`).
- `--force-auth`: ignore the cached session and log in again during a scan.
- `--force-scan`: ignore cached reservations and fetch fresh data.

The session cookie is cached at `~/.cache/clem/session.json`. Successful scans save reservation JSON at `~/.cache/clem/reservations.json`; its modification time determines whether it is still fresh (two hours). A fresh cache hit makes no portal API or login requests and logs its age to stderr. Use `--force-scan` to bypass it. Any fetch or parsing failure aborts the run rather than returning partial results.

## Scope and limitations

This project is tailored to the Thoiry portal's current dashboard and reservation-calendar responses. It reports booked days available through those views; it does not report holiday programs or one-off activities that are absent from the dashboard. Portal markup or API changes may require updates to the parser.
