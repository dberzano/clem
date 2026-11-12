"""HTTP session with automatic login and a persisted cookie jar.

Only GET is exposed publicly; the single POST is the login form.
The portal rate-limits logins (even successful ones), so cookies are cached
on disk and a login is performed only when the cached session is rejected.
"""
import json
import os
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from .config import BASE_URL, SESSION_PATH, load_credentials
from .errors import ClemError
from .progress import Reporter

AUTH_MARKER = 'estAuthentifier = "True"'
RATE_LIMIT_MARKER = "dépassé le nombre maximum de tentatives"
DASHBOARD = "CompteCitoyen"


class Client:
    def __init__(self, session_path: Path = SESSION_PATH, reporter: Reporter | None = None):
        self._session_path = session_path
        self._reporter = reporter or Reporter()
        self._http = httpx.Client(
            base_url=BASE_URL, follow_redirects=True, timeout=30,
            headers={"User-Agent": "clem-cli/0.1"},
        )
        self._load_cookies()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- public ---------------------------------------------------------

    def dashboard_html(self) -> str:
        """Authenticated GET of the dashboard; logs in transparently if needed."""
        rep = self._reporter
        rep.status("loading dashboard", 0)
        if self._http.cookies:
            html = self._fetch(DASHBOARD)
            if AUTH_MARKER in html:
                rep.status("loading dashboard", 5)
                rep.status("reading dashboard", 10)
                return html
        rep.status("logging in", 5)
        html = self._login()
        self._save_cookies()
        rep.status("reading dashboard", 10)
        return html

    def get_text(self, path: str) -> str:
        """Authenticated GET returning the body; the session must already be established."""
        r = self._get(path)
        if r.status_code != 200:
            raise ClemError("upstream", f"GET {path}: HTTP {r.status_code}")
        return r.text

    def get_json(self, path: str, params: dict) -> dict:
        r = self._get(path, params)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
            raise ClemError("upstream", f"GET {path}: HTTP {r.status_code} ({r.headers.get('content-type')})")
        return r.json()

    def clear_session(self) -> None:
        self._session_path.unlink(missing_ok=True)
        self._http.cookies.clear()

    # -- internals ------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> httpx.Response:
        try:
            return self._http.get(path, params=params)
        except httpx.HTTPError as e:
            raise ClemError("upstream", f"GET {path} failed: {e}") from e

    def _fetch(self, path: str) -> str:
        return self._get(path).text

    def _login(self) -> str:
        username, password = load_credentials()
        self._http.cookies.clear()
        try:
            page = self._http.get("")
            token_input = BeautifulSoup(page.text, "html.parser").select_one(
                'input[name="__RequestVerificationToken"]'
            )
            if token_input is None:
                raise ClemError("upstream", "Login page has no __RequestVerificationToken")
            r = self._http.post(
                "Home/Logon",
                data={
                    "__RequestVerificationToken": token_input["value"],
                    "username": username,
                    "password": password,
                },
                headers={"Referer": str(page.url)},
            )
        except httpx.HTTPError as e:
            raise ClemError("upstream", f"Login request failed: {e}") from e
        if AUTH_MARKER in r.text:
            return r.text
        if RATE_LIMIT_MARKER in r.text:
            raise ClemError("rate_limited", "Too many login attempts; retry in a few minutes")
        raise ClemError("auth_failed", "Login rejected (check username/password)")

    def _load_cookies(self) -> None:
        try:
            entries = json.loads(self._session_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return
        for c in entries:
            self._http.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])

    def _save_cookies(self) -> None:
        entries = [
            {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
            for c in self._http.cookies.jar
        ]
        self._session_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._session_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(entries, f)
