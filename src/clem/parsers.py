import datetime as dt
import re

from bs4 import BeautifulSoup

from .errors import ClemError
from .models import Kid, Registration, Reservation

_ID = re.compile(r"idDynamic=(\d+)")
_PREFIX = "Accéder à la fiche de "
_REG_LINK = re.compile(r"Reservation/(\d+)/(\d+)/(\d+)/(\d+)")
_PAGE_IDS = re.compile(
    r"var idPer\s*=\s*(\d+);\s*var idIns\s*=\s*(\d+);\s*var idLie\s*=\s*(\d+);\s*var idClg\s*=\s*(\d+);"
)


def _clean(text: str) -> str:
    return " ".join(text.split())


def parse_kids(dashboard_html: str) -> list[Kid]:
    """Kids from the 'Membres foyer' section of the dashboard (doc §5.1)."""
    soup = BeautifulSoup(dashboard_html, "html.parser")
    kids = []
    for tile in soup.select('div[id^="divMembresDalle_"]'):
        link = tile.select_one('a[href*="DetailPersonne?idDynamic="]')
        if link is None:
            continue
        kids.append(Kid(
            id=int(_ID.search(link["href"]).group(1)),
            name=link.get("title", "").removeprefix(_PREFIX).strip(),
        ))
    if not kids:
        raise ClemError("upstream", "No kids found on the dashboard (markup changed?)")
    return kids


def parse_registrations(dashboard_html: str) -> list[Registration]:
    """Registrations from table #tblDalleDetail_Reservation (doc §5.2)."""
    soup = BeautifulSoup(dashboard_html, "html.parser")
    out = []
    for link in soup.select('table#tblDalleDetail_Reservation a[href*="NouvelleDemandeReservation/"]'):
        match = _REG_LINK.search(link["href"])
        cells = [_clean(td.get_text(" ")) for td in link.find_parent("tr").select("td")]
        if match is None or len(cells) < 4:
            raise ClemError("upstream", f"Unexpected registration row: {link['href']}")
        kid, ins, lieu, clg = map(int, match.groups())
        out.append(Registration(
            kid_id=kid, ins=ins, lieu=lieu, clg=clg, activity=cells[2], place=cells[3],
        ))
    if not out:
        raise ClemError("upstream", "No registrations found on the dashboard (markup changed?)")
    return out


def parse_page_ids(page_html: str) -> tuple[int, int, int, int]:
    """(idPer, idIns, idLie, idClg) from the reservation page script (doc §4)."""
    match = _PAGE_IDS.search(page_html)
    if match is None:
        raise ClemError("upstream", "Reservation page has no idPer/idIns/idLie/idClg")
    return tuple(map(int, match.groups()))


def extract_reservations(calendar: dict, reg: Registration, kid_name: str) -> list[Reservation]:
    """Booked days of a registration calendar (doc §5.3).

    Booked <=> (nbConsoDemandePrecedente ?? nbConsoBase) > 0
    Editable <=> day.isActif and unit.isActif
    """
    try:
        units = {u["idUnite"]: _clean(u["libUnite"]) for u in calendar["listeUnitesInscr"]}
        out = []
        for week in calendar["listeSemainesAffichees"]:
            for day in week["listeJoursAffiches"]:
                for unit in day["listeUnitesJour"]:
                    qty = unit["nbConsoDemandePrecedente"]
                    if qty is None:
                        qty = unit["nbConsoBase"]
                    if not qty:
                        continue
                    out.append(Reservation(
                        kid_id=reg.kid_id, kid_name=kid_name, registration_id=reg.ins,
                        activity=reg.activity, place=reg.place, unit=units[unit["idUnite"]],
                        date=dt.datetime.strptime(str(day["idJour"]), "%Y%m%d").date(),
                        quantity=qty, editable=bool(day["isActif"] and unit["isActif"]),
                    ))
        return out
    except (KeyError, TypeError, ValueError) as e:
        raise ClemError("upstream", f"Unexpected calendar format: {e!r}") from e
