"""Fetch every reservation of every kid.

dashboard -> N registrations -> per registration (thread pool, one shared session):
    1. GET reservation page  (idPer; also required, else the calendar returns 500)
    2. GET calendar JSON
Any failure aborts the whole run: all results or none.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed

from .client import Client
from .errors import ClemError
from .models import Registration, Reservation
from .progress import FETCH_END, FETCH_START, Reporter
from .parsers import extract_reservations, parse_kids, parse_page_ids, parse_registrations

PAGE = "DemandeEnfance/NouvelleDemandeReservation/{kid}/{ins}/{lieu}/{clg}"
CALENDAR = "DemandeEnfance/NouvelleDemandeReservationGetCalendrier"


def _fetch_registration(
    client: Client, reg: Registration, kid_name: str, reporter: Reporter
) -> list[Reservation]:
    reporter.worker_started(reg.ins, f"{kid_name} / {reg.activity}")
    try:
        page = client.get_text(PAGE.format(kid=reg.kid_id, ins=reg.ins, lieu=reg.lieu, clg=reg.clg))
        id_per, ins, lieu, clg = parse_page_ids(page)
        reporter.advance()
        reporter.worker_step(reg.ins, "downloading calendar")
        calendar = client.get_json(
            CALENDAR, {"idPer": id_per, "idIns": ins, "idLie": lieu, "idClg": clg}
        )
        reservations = extract_reservations(calendar, reg, kid_name)
        reporter.advance()
        return reservations
    except ClemError as e:
        raise ClemError(
            e.code, f"registration {reg.ins} ({kid_name}, {reg.activity}): {e.message}"
        ) from e
    finally:
        reporter.worker_done(reg.ins)


def fetch_reservations(client: Client, parallel: int, reporter: Reporter) -> list[Reservation]:
    dashboard = client.dashboard_html()
    kids = parse_kids(dashboard)
    kid_names = {k.id: k.name for k in kids}
    registrations = parse_registrations(dashboard)
    for reg in registrations:
        if reg.kid_id not in kid_names:
            raise ClemError("upstream", f"Registration {reg.ins} belongs to unknown kid {reg.kid_id}")
    total = len(registrations)
    reporter.status(f"fetching reservations: 0 / {total}", FETCH_START)
    reporter.begin_fetch(2 * total)

    reservations: list[Reservation] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = [
            pool.submit(_fetch_registration, client, reg, kid_names[reg.kid_id], reporter)
            for reg in registrations
        ]
        try:
            for done, future in enumerate(as_completed(futures), start=1):
                reservations.extend(future.result())
                reporter.describe(f"fetching reservations: {done} / {total}")
        except BaseException:
            for f in futures:
                f.cancel()
            raise
    reporter.status("combining reservations", FETCH_END)
    reservations.sort(key=lambda r: (r.date, r.kid_id, r.registration_id))
    reporter.status("done", 100)
    return reservations
