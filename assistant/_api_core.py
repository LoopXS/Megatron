"""Framework-free core for retrieving Telegram API credentials.

This drives the my.telegram.org website (there is no official API for
creating ``api_id`` / ``api_hash`` pairs) using the same flow popular
scrapers use:

1. ``POST /auth/send_password`` -> Telegram sends a login code, returns a
   ``random_hash``.
2. ``POST /auth/login``         -> establishes the ``stel_*`` session cookies.
   The redesigned site reports failure with an HTTP error status; older
   versions returned the literal ``true``.
3. ``GET  /apps``               -> either an existing app's credentials, or a
   form carrying the ``hash`` needed to create one.
4. ``POST /apps/create``        -> creates the app (Telegram's side is flaky,
   so we retry), then re-read ``/apps`` for the credentials.

The page markup has changed over time (legacy ``.input-xlarge`` spans vs the
current ``.cred`` blocks that carry values in ``data-value`` attributes), so
extraction recognises both shapes and identifies values by their form.

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
DEFAULT_PLATFORM = "other"
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
# ``api_id`` / ``api_hash`` label followed by its value, e.g. ``api_id: 1234567``.
_API_ID_RE = re.compile(r"api[\s_-]?id[^0-9]{0,200}?(\d{4,})", re.IGNORECASE)
_API_HASH_RE = re.compile(r"api[\s_-]?hash[^0-9a-f]{0,200}?([0-9a-f]{32})", re.IGNORECASE)
_MASK_CHARS = frozenset("\u2022\u00b7.*\u25cf")


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
    status = getattr(response, "status_code", 200) or 200
    try:
        payload = response.json()
    except ValueError:
        if status >= 400:
            raise ApiCredsError(
                "api_err_send_code", detail=(response.text or "")[:120]
            ) from None
        raise ApiCredsError("api_err_unexpected") from None
    if not isinstance(payload, dict):
        raise ApiCredsError("api_err_unexpected")
    random_hash = payload.get("random_hash")
    if random_hash:
        return random_hash
    detail = payload.get("text") or payload.get("error") or payload.get("message") or ""
    raise ApiCredsError("api_err_send_code", detail=str(detail)[:120])


def submit_login_code(session, phone, random_hash, code):
    """Complete the website login; ``True`` when the code was accepted.

    The legacy site replied with the literal ``true`` (HTTP 200) on success and
    the error message in the body otherwise.  The redesigned site instead
    signals failure with a non-2xx status and a JSON body, and returns an empty
    or JSON body on success, so the HTTP status is the reliable signal there.
    """
    response = session.post(
        LOGIN_URL,
        data={"phone": phone, "random_hash": random_hash, "password": code},
        timeout=HTTP_TIMEOUT,
    )
    status = getattr(response, "status_code", 200) or 200
    text = (response.text or "").strip()
    if text.lower() == "true":
        return True
    if status >= 400:
        return False
    # Redesigned endpoint: any 2xx with an empty, JSON or (redirect-followed)
    # HTML body is a success.
    if not text or text[0] in "{<[":
        return True
    # Legacy endpoint returned the failure reason as plain text with HTTP 200.
    return False


def _is_api_id(value):
    """True when ``value`` looks like a Telegram ``api_id`` (4-10 digits)."""
    value = (value or "").strip()
    return value.isdigit() and 4 <= len(value) <= 10


def _is_api_hash(value):
    """True when ``value`` looks like a 32-character hex ``api_hash``."""
    return _HEX_HASH_RE.fullmatch((value or "").strip()) is not None


def _first(values, predicate):
    for value in values:
        value = (value or "").strip()
        if predicate(value):
            return value
    return None


def _normalise_label(text):
    """``"App api_id:"`` -> ``"appapiid"`` (labels vary between layouts)."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _strip_attr(node, *names):
    for name in names:
        value = node.get(name)
        if value:
            value = str(value).strip()
            if value:
                return value
    return None


def _cred_value(cred):
    """Value of a redesigned ``.cred`` block (``data-value``/``data-copy``/``.vv``)."""
    value_el = cred.select_one(".v")
    if value_el is not None:
        value = _strip_attr(value_el, "data-value", "data-copy")
        if value:
            return value
    copy_btn = cred.select_one("[data-copy]")
    if copy_btn is not None:
        value = _strip_attr(copy_btn, "data-copy")
        if value:
            return value
    vv = cred.select_one(".vv")
    if vv is not None:
        text = vv.get_text(strip=True)
        # ``.vv`` is filled with bullet characters while the value is masked.
        if text and not set(text) <= _MASK_CHARS:
            return text
    return None


def _extract_credentials(soup, html):
    """Best-effort pull of ``(api_id, api_hash)`` from an ``/apps`` page.

    Handles both the redesigned layout (``.cred`` blocks whose value lives in
    ``data-value``/``data-copy``) and the legacy one (``.input-xlarge`` spans /
    readonly inputs), then falls back to labelled text and pattern matching.
    Values are identified by their shape, so their order never matters.
    """
    api_id = None
    api_hash = None

    # 1) Redesigned layout: label (.k) + value (data-value / data-copy / .vv).
    for cred in soup.select(".cred"):
        key_el = cred.select_one(".k")
        if key_el is None:
            continue
        label = _normalise_label(key_el.get_text(" ", strip=True))
        value = _cred_value(cred)
        if not value:
            continue
        if api_id is None and "apiid" in label and _is_api_id(value):
            api_id = value
        if api_hash is None and "apihash" in label and _is_api_hash(value):
            api_hash = value
    if api_id and api_hash:
        return api_id, api_hash

    # 2) Explicit ids (``#app_id`` / ``#app_hash`` / ``#api_id`` ...).
    for node in soup.find_all(id=True):
        node_id = _normalise_label(node.get("id"))
        if not node_id:
            continue
        value = _strip_attr(node, "data-value", "data-copy") or node.get_text(strip=True)
        value = (value or "").strip()
        if api_id is None and node_id in ("appid", "apiid") and _is_api_id(value):
            api_id = value
        if (
            api_hash is None
            and node_id in ("apphash", "apihash")
            and _is_api_hash(value)
        ):
            api_hash = value
    if api_id and api_hash:
        return api_id, api_hash

    # 3) Legacy layout: ``.input-xlarge`` spans + readonly inputs.
    legacy = [el.get_text(strip=True) for el in soup.select(".input-xlarge")]
    legacy += [
        (node.get("value") or "").strip()
        for node in soup.find_all("input")
        if node.get("readonly") is not None and node.get("value")
    ]
    api_id = api_id or _first(legacy, _is_api_id)
    api_hash = api_hash or _first(legacy, _is_api_hash)
    if api_id and api_hash:
        return api_id, api_hash

    # 4) Any data-copy / data-value attribute on the page.
    generic = []
    for node in soup.find_all(True):
        for attr in ("data-copy", "data-value"):
            value = node.get(attr)
            if value:
                generic.append(str(value).strip())
    api_id = api_id or _first(generic, _is_api_id)
    api_hash = api_hash or _first(generic, _is_api_hash)
    if api_id and api_hash:
        return api_id, api_hash

    # 5) Labelled text fallback (e.g. "App api_id: 1234567").
    text = soup.get_text(" ", strip=True)
    if api_id is None:
        match = _API_ID_RE.search(text)
        if match:
            api_id = match.group(1)
    if api_hash is None:
        match = _API_HASH_RE.search(text)
        if match:
            api_hash = match.group(1)
    if api_id and api_hash:
        return api_id, api_hash

    return None


def _platform_options(soup):
    """Values offered by the create form's platform field (radios or select)."""
    values = []
    for node in soup.find_all("input"):
        if node.get("name") == "app_platform":
            value = (node.get("value") or "").strip()
            if value:
                values.append(value)
    for node in soup.find_all("select"):
        if node.get("name") not in (None, "app_platform"):
            continue
        for option in node.find_all("option"):
            value = (option.get("value") or option.get_text(strip=True) or "").strip()
            if value:
                values.append(value)
    seen = set()
    unique = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _choose_platform(options):
    """Pick a valid ``app_platform`` from the form, preferring neutral ones."""
    options = [option for option in (options or []) if option]
    for preferred in ("other", "desktop", "web", "android", "ios", "windows", "linux"):
        if preferred in options:
            return preferred
    return options[0] if options else DEFAULT_PLATFORM


def parse_apps_page(html):
    """Classify an ``/apps`` page.

    Returns ``{"exists": True, "api_id", "api_hash"}`` when the account
    already has an application, or ``{"exists": False, "hash", "platforms"}``
    when the create form is shown.  Raises :class:`ApiCredsError` otherwise.
    """
    soup = BeautifulSoup(html or "", "html.parser")

    # Credentials win: the redesigned page keeps a save form (with its own
    # ``hash`` field) even when an application already exists.
    credentials = _extract_credentials(soup, html or "")
    if credentials:
        return {
            "exists": True,
            "api_id": credentials[0],
            "api_hash": credentials[1],
        }

    # A credentials block we could not read means the markup changed; fail
    # loudly instead of trying to create a second application.
    if soup.select_one(".cred") is not None or soup.select_one(".creds") is not None:
        raise ApiCredsError("api_err_parse")

    hash_input = soup.find("input", {"name": "hash"})
    create_form = soup.find("form", {"id": "app_create_form"})
    if hash_input is not None or create_form is not None:
        return {
            "exists": False,
            "hash": hash_input.get("value") if hash_input is not None else None,
            "platforms": _platform_options(soup),
        }

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

    platform = _choose_platform(app.get("platforms"))
    for attempt in range(max(1, int(attempts))):
        if not app.get("hash"):
            break
        title, shortname = random_app_identity(attempt)
        create_app(session, app["hash"], title, shortname, platform=platform)
        app = fetch_app(session)
        if app.get("exists"):
            return app["api_id"], app["api_hash"]
        if app.get("platforms"):
            platform = _choose_platform(app["platforms"])

    raise ApiCredsError("api_err_create")
