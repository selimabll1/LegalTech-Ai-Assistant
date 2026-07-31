
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

try:
    from playwright.sync_api import (
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeoutError,
        sync_playwright,
    )
except ImportError:
    BrowserContext = Any
    Page = Any
    PlaywrightTimeoutError = TimeoutError
    sync_playwright = None

LEGALTECH_BROWSER_COLLECTOR_VERSION = "legaltech_browser_collector_v1_3_1_init_script_fix"

DEFAULT_BASE_URL = "https://annonces.legaltech.tn"
DEFAULT_STORAGE_STATE = Path("secrets/legaltech_storage_state.json")
DEFAULT_SESSION_STORAGE = Path("secrets/legaltech_session_storage.json")
DEFAULT_DOWNLOAD_DIR = Path("data/legaltech_browser_downloads")

ARTICLE_ROUTE_RE = re.compile(
    r"/article/(?P<source>[^/?#]+)/(?P<article_id>[^/?#]+)",
    re.I,
)

LOGIN_URL_HINTS = (
    "/login", "/signin", "/sign-in", "/auth", "/connexion",
)

class BrowserCollectorError(RuntimeError):
    pass

class AuthenticationRequired(BrowserCollectorError):
    pass

@dataclass(frozen=True)
class BrowserResult:
    result_key: str
    alert_url: str
    source: str
    article_id: str
    doc_id: str
    article_url: str
    list_page: int
    list_text: str

@dataclass(frozen=True)
class BrowserDetail:
    result_key: str
    article_url: str
    title: str
    visible_text: str
    source_fields: dict[str, str]
    detail_status: str
    error: str = ""

def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def parse_article_url(url: str, base_url: str = DEFAULT_BASE_URL) -> BrowserResult:
    absolute = urljoin(base_url.rstrip("/") + "/", url)
    parsed = urlparse(absolute)
    match = ARTICLE_ROUTE_RE.search(parsed.path)
    if not match:
        raise ValueError(f"URL d'article LegalTech non reconnue : {url}")

    source = match.group("source")
    article_id = match.group("article_id")
    doc_id = str((parse_qs(parsed.query).get("docId") or [""])[0]).strip()
    result_key = sha256(
        f"{source}|{article_id}|{doc_id}".encode("utf-8")
    ).hexdigest()

    return BrowserResult(
        result_key=result_key,
        alert_url="",
        source=source,
        article_id=article_id,
        doc_id=doc_id,
        article_url=absolute,
        list_page=0,
        list_text="",
    )

def _extract_value_from_lines(text: str, labels: tuple[str, ...]) -> str:
    lines = [normalize_space(x) for x in str(text or "").splitlines()]
    lines = [x for x in lines if x]
    for i, line in enumerate(lines):
        for label in labels:
            m = re.match(
                rf"^{re.escape(label)}\s*[:：\-]?\s*(.*)$",
                line,
                re.I,
            )
            if not m:
                continue
            inline = normalize_space(m.group(1))
            if inline:
                return inline
            if i + 1 < len(lines):
                return lines[i + 1]
    return ""

def parse_rne_visible_fields(text: str) -> dict[str, str]:
    """Parse visible RNE detail text without shifting label/value pairs.

    LegalTech often exposes RNE details as one flattened text block. The old
    line-oriented parser could therefore shift fields, e.g. denomination
    becoming "latin" or type_modification becoming "Bulletin N°".

    This parser changes only structured RNE extraction.
    """
    clean = normalize_space(text)
    if not clean:
        return {}

    field_aliases = [
        ("numero_publication", (
            "Annonce N°", "Annonce N°:", "Publication N°",
        )),
        ("type_publication", (
            "Type de publication", "Type publication",
        )),
        ("bulletin_numero", (
            "Bulletin N°", "Bulletin No",
        )),
        ("date_publication", (
            "Date publication", "Date Publication", "Date",
        )),
        ("identifiant_unique", (
            "Identifiant Unique", "Identifiant unique", "IU",
        )),
        ("capital", (
            "Capital social", "Capital",
        )),
        ("duree_societe", (
            "Durée de la société", "Durée société",
            "Duree societe", "Durée",
        )),
        ("categorie_registre", (
            "Type de registre", "Catégorie du registre",
            "Catégorie registre",
        )),
        ("responsable", (
            "1er responsable", "Nom du responsable",
            "Nom responsable", "Responsable",
        )),
        ("qualite_responsable", (
            "Qualité du responsable", "Qualité responsable",
            "Qualite responsable", "Qualité",
        )),
        ("nom_commercial", (
            "Nom commercial",
        )),
        ("type_modification", (
            "Type de modification", "Type modification",
        )),
        ("type_modification_ar", (
            "نوع التحيين",
        )),
        ("type_demande_reservation", (
            "Type demande de réservation",
            "Type demande de reservation",
        )),
        ("numero_certificat", (
            "N° certificat", "Numéro certificat",
            "Numero certificat",
        )),
        ("date_reservation", (
            "Date réservation", "Date reservation",
        )),
        ("delai_reservation", (
            "Délai de réservation", "Delai de reservation",
        )),
        ("type_reservation", (
            "Type réservation", "Type reservation",
        )),
        ("denomination_latin", (
            "Dénomination latin", "Denomination latin",
        )),
        ("denomination_ar", (
            "Dénomination Ar", "Denomination Ar",
        )),
        ("adresse", (
            "Adresse", "Siège social", "Siege social",
        )),
        ("activite", (
            "Activité", "Activite",
        )),
        ("date_creation", (
            "Date de création", "Date création",
            "Date de creation",
        )),
        ("numero_borne", (
            "N° BORNE", "N° Borne",
            "Numéro BORNE", "Numéro Borne",
        )),
    ]

    stop_markers = (
        "Consultez l'Etat du Registre RNE",
        "Consultez l’État du Registre RNE",
        "Créer une alerte",
        "Creer une alerte",
        "Registre National des Entreprises",
    )

    alias_to_key = {}
    tokens = []

    for key, aliases in field_aliases:
        for alias in aliases:
            normalized = normalize_space(alias)
            alias_to_key[normalized.casefold()] = key
            tokens.append(normalized)

    tokens.extend(stop_markers)
    tokens = sorted(set(tokens), key=len, reverse=True)

    token_rx = re.compile(
        r"(?<!\w)("
        + "|".join(re.escape(token) for token in tokens)
        + r")(?!\w)",
        re.I,
    )

    matches = list(token_rx.finditer(clean))
    out = {}

    for index, match in enumerate(matches):
        matched_label = normalize_space(match.group(1))
        key = alias_to_key.get(matched_label.casefold())
        if not key:
            continue

        next_start = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(clean)
        )

        value = clean[match.end():next_start]
        value = normalize_space(value.strip(" :：-–—,;"))

        if value and key not in out:
            out[key] = value

    if out.get("denomination_latin"):
        out["denomination"] = out["denomination_latin"]
    elif out.get("nom_commercial"):
        out["denomination"] = out["nom_commercial"]
    else:
        fallback = _extract_value_from_lines(
            text,
            (
                "Dénomination sociale",
                "Dénomination",
                "Denomination",
                "Nom société",
                "Nom de la société",
            ),
        )
        if fallback:
            out["denomination"] = fallback

    return out

class LegalTechBrowserCollector:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        storage_state_path: str | Path = DEFAULT_STORAGE_STATE,
        session_storage_path: str | Path = DEFAULT_SESSION_STORAGE,
        download_dir: str | Path = DEFAULT_DOWNLOAD_DIR,
        headless: bool = False,
        slow_mo_ms: int = 0,
    ):
        self.base_url = base_url.rstrip("/")
        self.storage_state_path = Path(storage_state_path)
        self.session_storage_path = Path(session_storage_path)
        self.download_dir = Path(download_dir)
        self.headless = bool(headless)
        self.slow_mo_ms = max(0, int(slow_mo_ms))

        self.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = None
        self.browser = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def _session_snapshot(self) -> dict[str, dict[str, str]]:
        if not self.session_storage_path.exists():
            return {}
        try:
            data = json.loads(
                self.session_storage_path.read_text(encoding="utf-8")
            )
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def __enter__(self):
        if sync_playwright is None:
            raise BrowserCollectorError(
                "Playwright absent. Exécutez: "
                "python -m pip install playwright && "
                "python -m playwright install chromium"
            )

        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo_ms,
        )

        kwargs = {
            "accept_downloads": True,
            "viewport": {"width": 1500, "height": 1000},
        }
        if self.storage_state_path.exists():
            kwargs["storage_state"] = str(self.storage_state_path)

        self.context = self.browser.new_context(**kwargs)

        session_data = self._session_snapshot()
        if session_data:
            # BrowserContext.add_init_script accepts only a script/path in the
            # Python Playwright API; it does not accept a second positional
            # argument for data. Embed the local JSON snapshot safely into the
            # script instead.
            snapshot_json = json.dumps(
                session_data,
                ensure_ascii=False,
            ).replace("</", "<\\/")

            init_script = f"""
            (() => {{
                const snapshot = {snapshot_json};
                try {{
                    const values = snapshot[window.location.origin];
                    if (!values) return;

                    for (const [key, value] of Object.entries(values)) {{
                        window.sessionStorage.setItem(key, String(value));
                    }}
                }} catch (e) {{
                    // Ignore malformed/unsupported sessionStorage values.
                }}
            }})();
            """

            self.context.add_init_script(script=init_script)

        self.page = self.context.new_page()
        return self

    def _require_page(self) -> Page:
        if self.page is None:
            raise BrowserCollectorError("Navigateur non lancé.")
        return self.page

    def save_full_state(self) -> None:
        if self.context is None:
            return

        self.context.storage_state(path=str(self.storage_state_path))

        snapshot: dict[str, dict[str, str]] = {}
        for page in list(self.context.pages):
            try:
                origin = page.evaluate("window.location.origin")
                if not origin or origin == "null":
                    continue
                values = page.evaluate(
                    "Object.fromEntries(Object.entries(window.sessionStorage))"
                )
                if isinstance(values, dict):
                    snapshot[str(origin)] = {
                        str(k): str(v) for k, v in values.items()
                    }
            except Exception:
                pass

        if snapshot:
            self.session_storage_path.write_text(
                json.dumps(snapshot, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.context is not None:
                try:
                    self.save_full_state()
                except Exception:
                    pass
                self.context.close()
            if self.browser is not None:
                self.browser.close()
        finally:
            if self._playwright is not None:
                self._playwright.stop()

    @staticmethod
    def _wait_settle(page: Page) -> None:
        try:
            page.locator("body").wait_for(state="attached", timeout=7000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

    def goto(self, url: str, timeout_ms: int = 30000) -> Page:
        page = self._require_page()
        error = None
        try:
            page.goto(
                url,
                wait_until="commit",
                timeout=min(timeout_ms, 15000),
            )
        except PlaywrightTimeoutError as exc:
            error = exc

        self._wait_settle(page)

        if error is not None:
            requested = urlparse(url).netloc.casefold()
            current = urlparse(str(page.url or "")).netloc.casefold()
            if not current or (requested and requested != current):
                raise BrowserCollectorError(
                    f"Navigation échouée. URL actuelle: {page.url}"
                ) from error

        return page

    def is_authenticated(self) -> bool:
        page = self._require_page()
        lower_url = str(page.url or "").casefold()
        if any(h in lower_url for h in LOGIN_URL_HINTS):
            return False

        try:
            inputs = page.locator("input[type='password']")
            for i in range(inputs.count()):
                if inputs.nth(i).is_visible():
                    return False
        except Exception:
            pass
        return True

    def ensure_authenticated(self, url: str | None = None):
        self.goto(url or self.base_url)
        if not self.is_authenticated():
            raise AuthenticationRequired(
                "Connexion LegalTech requise. Relancez "
                "`python -m scripts.legaltech_browser_login_v4`."
            )

    @staticmethod
    def _best_visible_text(page: Page) -> str:
        for selector in ("main", "[role='main']", "article", "body"):
            try:
                loc = page.locator(selector).first
                if loc.is_visible():
                    text = loc.inner_text(timeout=5000).strip()
                    if text:
                        return text
            except Exception:
                pass
        return ""

    def collect_detail(self, result: BrowserResult) -> BrowserDetail:
        page = self.goto(result.article_url)
        if not self.is_authenticated():
            raise AuthenticationRequired("Reconnexion LegalTech requise.")

        title = ""
        for selector in ("h1", "h2", "main h3"):
            try:
                t = normalize_space(
                    page.locator(selector).first.inner_text(timeout=1500)
                )
                if t:
                    title = t
                    break
            except Exception:
                pass
        if not title:
            title = normalize_space(page.title())

        text = self._best_visible_text(page)
        fields = (
            parse_rne_visible_fields(text)
            if result.source.casefold() == "rne"
            else {}
        )

        return BrowserDetail(
            result_key=result.result_key,
            article_url=result.article_url,
            title=title,
            visible_text=text,
            source_fields=fields,
            detail_status="COLLECTED",
        )

    def try_download_visible_document(
        self,
        result: BrowserResult,
        timeout_ms: int = 12000,
    ):
        page = self._require_page()
        if str(page.url) != result.article_url:
            self.goto(result.article_url)

        candidates = []
        for role in ("button", "link"):
            for pattern in (
                re.compile("télécharger", re.I),
                re.compile("telecharger", re.I),
                re.compile("download", re.I),
            ):
                loc = page.get_by_role(role, name=pattern)
                for i in range(loc.count()):
                    candidates.append(loc.nth(i))

        for candidate in candidates:
            try:
                if not candidate.is_visible():
                    continue
                with page.expect_download(timeout=timeout_ms) as info:
                    candidate.click()
                download = info.value
                name = normalize_space(download.suggested_filename)
                if not name:
                    name = f"{result.article_id}.pdf"
                safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
                destination = self.download_dir / safe
                download.save_as(str(destination))
                return "COLLECTED", destination
            except Exception:
                continue
        return "NOT_CAPTURED", None
