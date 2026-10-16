"""Framework-free core for retrieving Telegram API credentials.

This drives the my.telegram.org website (there is no official API for
creating ``api_id`` / ``api_hash`` pairs) using the same flow popular
scrapers use:

1. ``POST /auth/send_password`` -> Telegram sends a login code, returns a
   ``random_hash``.
2. ``POST /auth/login``         -> establishes the ``stel_*`` session cookies.
3. ``GET  /apps``               -> either an existing app's credentials, or a
   form carrying the ``hash`` needed to create one.
4. ``POST /apps/create``        -> creates the app (Telegram's side is flaky,
   so we retry), then re-read ``/apps`` for the credentials.

The module never imports ``requests`` and takes the HTTP session as an
argument, which keeps it fully unit-testable with a fake session and makes
it usable over any client.  ``random`` is only used for app name generation.
"""

import random
import re
import string

from bs4 import BeautifulSoup

MY_TELEGRAM_ORG = "https://my.telegram.org"
WEB_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 20
DEFAULT_PLATFORM = "desktop"
DEFAULT_APP_URL = "https://telegram.org"
DEFAULT_APP_DESC = "Personal application"

SEND_PASSWORD_URL = MY_TELEGRAM_ORG + "/auth/send_password"
LOGIN_URL = MY_TELEGRAM_ORG + "/auth/login"
APPS_URL = MY_TELEGRAM_ORG + "/apps"
CREATE_APP_URL = MY_TELEGRAM_ORG + "/apps/create"

# Friendly, neutral words used to build random app names.  Telegram rejects
# obviously-reused names, so each attempt is randomised.
_APP_WORDS = (
    "alpha",
    "bravo",
    "delta",
    "echo",
    "gamma",
    "nova",
    "orbit",
    "pixel",
    "quartz",
    "raven",
    "solar",
    "titan",
    "vega",
    "zephyr",
)

_HEX_HASH_RE = re.compile(r"\b([0-9a-f]{32})\b", re.IGNORECASE)
_API_ID_RE = re.compile(r"api_id[^0-9]{0,80}(\d{4,})", re.IGNORECASE)


class ApiCredsError(Exception):
    """A failure that should be shown to the user.

    ``key`` is a string catalogue key; ``kwargs`` are optional ``.format``
    values for that string.
    """

    def __init__(self, key, **kwargs):
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs


def random_app_identity(attempt=0):
    """Return a ``(title, shortname)`` pair for the create-app form.

    Names are randomised on every call so retries after a rejected
    submission use fresh values.
    """
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    word = random.choice(_APP_WORDS)
    title = "App {0} {1}".format(word.capitalize(), suffix)
    shortname = "app" + suffix + str(int(attempt) % 10)
    shortname = "".join(ch for ch in shortname if ch.isalnum())
    return title, shortname


def request_login_code(session, phone):
    """Ask my.telegram.org to send a login code; return the ``random_hash``."""
    response = session.post(
        SEND_PASSWORD_URL,
        data={"phone": phone},
        timeout=HTTP_TIMEOUT,
    )
    try:
        payload = response.json()
    except ValueError:
        raise ApiCredsError("api_err_unexpected") from None
    if not isinstance(payload, dict):
        raise ApiCredsError("api_err_unexpected")
    random_hash = payload.get("random_hash")
    if random_hash:
        return random_hash
    detail = payload.get("error") or payload.get("message") or ""
    raise ApiCredsError("api_err_send_code", detail=str(detail)[:120])


def submit_login_code(session, phone, random_hash, code):
    """Complete the website login; ``True`` when the code was accepted."""
    response = session.post(
        LOGIN_URL,
        data={"phone": phone, "random_hash": random_hash, "password": code},
        timeout=HTTP_TIMEOUT,
    )
    return response.text.strip().lower() == "true"


def _extract_credentials(soup, html):
    """Best-effort pull of ``(api_id, api_hash)`` from an ``/apps`` page."""
    spans = soup.select(".input-xlarge")
    if len(spans) >= 2:
        api_id = spans[0].get_text(strip=True)
        api_hash = spans[1].get_text(strip=True)
        if api_id.isdigit() and _HEX_HASH_RE.fullmatch(api_hash.strip()):
            return api_id, api_hash.strip()

    inputs = [
        node.get("value", "").strip()
        for node in soup.find_all("input")
        if node.get("readonly") is not None and node.get("value")
    ]
    if len(inputs) >= 2:
        api_id, api_hash = inputs[0], inputs[1]
        if api_id.isdigit() and _HEX_HASH_RE.fullmatch(api_hash):
            return api_id, api_hash

    id_match = _API_ID_RE.search(html)
    hash_match = _HEX_HASH_RE.search(html)
    if id_match and hash_match:
        return id_match.group(1), hash_match.group(1)
    return None


def parse_apps_page(html):
    """Classify an ``/apps`` page.

    Returns ``{"exists": True, "api_id", "api_hash"}`` when the account
    already has an application, or ``{"exists": False, "hash"}`` when the
    create form is shown.  Raises :class:`ApiCredsError` otherwise.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string

    has_form = soup.find("input", {"name": "hash"}) is not None
    looks_configured = "configuration" in title.lower()

    if looks_configured or not has_form:
        credentials = _extract_credentials(soup, html or "")
        if credentials:
            return {
                "exists": True,
                "api_id": credentials[0],
                "api_hash": credentials[1],
            }

    if has_form:
        return {"exists": False, "hash": soup.find("input", {"name": "hash"}).get("value")}

    raise ApiCredsError("api_err_parse")


def fetch_app(session):
    """GET ``/apps`` and classify the result (see :func:`parse_apps_page`)."""
    response = session.get(APPS_URL, timeout=HTTP_TIMEOUT)
    return parse_apps_page(response.text)


def create_app(session, app_hash, title, shortname, platform=DEFAULT_PLATFORM, description=DEFAULT_APP_DESC):
    """POST the create-application form.  Returns the raw response."""
    return session.post(
        CREATE_APP_URL,
        data={
            "hash": app_hash,
            "app_title": title,
            "app_shortname": shortname,
            "app_url": DEFAULT_APP_URL,
            "app_platform": platform,
            "app_desc": description,
        },
        timeout=HTTP_TIMEOUT,
    )


def complete_credentials(session, phone, random_hash, code, attempts=5):
    """Log in and return ``(api_id, api_hash)`` for the account.

    Creates an application when the account has none, retrying the flaky
    create step up to ``attempts`` times with fresh names.
    """
    if not submit_login_code(session, phone, random_hash, code):
        raise ApiCredsError("api_err_bad_code")

    app = fetch_app(session)
    if app.get("exists"):
        return app["api_id"], app["api_hash"]

    for attempt in range(max(1, int(attempts))):
        title, shortname = random_app_identity(attempt)
        create_app(session, app["hash"], title, shortname)
        app = fetch_app(session)
        if app.get("exists"):
            return app["api_id"], app["api_hash"]

    raise ApiCredsError("api_err_create")
