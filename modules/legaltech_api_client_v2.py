"""Client ciblé pour les endpoints LegalTech observés dans le navigateur.

Le token PDF est chargé depuis un fichier local non versionné. Les requêtes
supportées sont :
- résultats d'une alerte enregistrée ;
- recherche d'articles ;
- génération d'un PDF Base64 à partir d'un article.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import base64
import binascii
import json
from pathlib import Path
import re
import time
from typing import Any, Iterable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LEGALTECH_API_CLIENT_VERSION = "legaltech_api_client_v2"


class LegalTechAPIError(RuntimeError):
    pass


class LegalTechConfigError(LegalTechAPIError):
    pass


class LegalTechTokenError(LegalTechAPIError):
    pass


@dataclass(frozen=True)
class LegalTechArticle:
    source_id: str
    doc_id: str
    reference: str
    title: str
    language: str
    article_text: str
    published_at: str
    source: str
    file: str
    page: int | None
    raw_hit: dict[str, Any]

    @property
    def filename(self) -> str:
        base = self.reference or self.doc_id or self.source_id or "annonce"
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .")
        return f"{cleaned or 'annonce'}.pdf"


@dataclass(frozen=True)
class SavedPDF:
    path: Path
    sha256: str
    size_bytes: int


def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise LegalTechConfigError(f"Fichier introuvable : {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise LegalTechConfigError(
            f"JSON invalide dans {file_path} : {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise LegalTechConfigError(
            f"{file_path} doit contenir un objet JSON."
        )
    return payload


def _safe_https_url(value: str, allowed_hosts: Iterable[str]) -> str:
    parsed = urlparse(value)
    allowed = {host.casefold() for host in allowed_hosts}
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in allowed:
        raise LegalTechConfigError(f"URL refusée : {value}")
    return value


def _article_from_hit(hit: dict[str, Any]) -> LegalTechArticle:
    source = hit.get("_source", hit)
    if not isinstance(source, dict):
        raise LegalTechAPIError("Structure d'article invalide : _source absent.")

    page_value = source.get("page")
    try:
        page = int(page_value) if page_value is not None else None
    except (TypeError, ValueError):
        page = None

    return LegalTechArticle(
        source_id=str(hit.get("_id") or source.get("doc_id") or "").strip(),
        doc_id=str(source.get("doc_id") or "").strip(),
        reference=str(source.get("reference") or "").strip(),
        title=str(source.get("title") or "").strip(),
        language=str(source.get("lang") or "").strip(),
        article_text=str(source.get("articleText") or ""),
        published_at=str(source.get("publishedAt") or "").strip(),
        source=str(source.get("source") or "").strip(),
        file=str(source.get("file") or "").strip(),
        page=page,
        raw_hit=hit,
    )


def normalize_articles(payload: dict[str, Any], mode: str) -> list[LegalTechArticle]:
    if mode == "alert_results":
        raw_items = payload.get("articles", [])
    elif mode == "article_search":
        hits = payload.get("hits", {})
        raw_items = hits.get("hits", []) if isinstance(hits, dict) else []
    else:
        raise LegalTechConfigError(f"Mode inconnu : {mode}")

    if not isinstance(raw_items, list):
        raise LegalTechAPIError("La réponse ne contient pas une liste d'articles.")

    articles: list[LegalTechArticle] = []
    for item in raw_items:
        if isinstance(item, dict):
            articles.append(_article_from_hit(item))
    return articles


def decode_pdf_base64(value: str) -> bytes:
    if not isinstance(value, str) or not value.strip():
        raise LegalTechAPIError("La réponse PDF est vide.")

    encoded = value.strip()
    if encoded.startswith("data:"):
        marker = "base64,"
        position = encoded.find(marker)
        if position < 0:
            raise LegalTechAPIError("Data URI PDF sans contenu Base64.")
        encoded = encoded[position + len(marker):]

    encoded = "".join(encoded.split())
    padding = (-len(encoded)) % 4
    if padding:
        encoded += "=" * padding

    try:
        data = base64.b64decode(encoded, validate=False)
    except (ValueError, binascii.Error) as exc:
        raise LegalTechAPIError("Base64 PDF invalide.") from exc

    if not data.startswith(b"%PDF"):
        raise LegalTechAPIError(
            "Le contenu décodé ne commence pas par la signature %PDF."
        )
    return data


class LegalTechAPIClient:
    def __init__(
        self,
        config: dict[str, Any],
        secrets: dict[str, Any],
    ) -> None:
        self.config = config
        self.mode = str(config.get("mode", "alert_results")).strip()
        self.api_base_url = str(config.get("api_base_url", "")).rstrip("/")
        self.frontend_base_url = str(
            config.get("frontend_base_url", "")
        ).rstrip("/")

        api_host = urlparse(self.api_base_url).hostname or ""
        frontend_host = urlparse(self.frontend_base_url).hostname or ""
        self.allowed_hosts = {api_host.casefold(), frontend_host.casefold()}
        if not all(self.allowed_hosts):
            raise LegalTechConfigError("URLs de base manquantes ou invalides.")

        endpoints = config.get("endpoints", {})
        if not isinstance(endpoints, dict):
            raise LegalTechConfigError("'endpoints' doit être un objet JSON.")

        self.alert_results_url = _safe_https_url(
            str(endpoints.get("alert_results", "")),
            self.allowed_hosts,
        )
        self.article_search_url = _safe_https_url(
            str(endpoints.get("article_search", "")),
            self.allowed_hosts,
        )
        self.pdf_url = _safe_https_url(
            str(endpoints.get("pdf_generation", "")),
            self.allowed_hosts,
        )

        self.pdf_token = str(secrets.get("pdf_token", "")).strip()
        if not self.pdf_token:
            raise LegalTechTokenError(
                "Le token PDF est absent de secrets/legaltech_session.local.json."
            )

        self.timeout = max(10, int(config.get("timeout_seconds", 60)))
        self.delay = max(0.0, float(config.get("min_delay_seconds", 1.5)))
        self.max_pdf_bytes = max(1, int(config.get("max_pdf_mb", 100))) * 1024 * 1024
        self.last_request_at = 0.0

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.frontend_base_url,
            "Referer": self.frontend_base_url + "/",
            "User-Agent": (
                "UGFS-LegalTech-Collector/2.0 "
                "(internal authorized integration)"
            ),
        })

        retry = Retry(
            total=4,
            connect=3,
            read=3,
            status=4,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "POST", "OPTIONS"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    @classmethod
    def from_files(
        cls,
        config_path: str | Path,
        session_path: str | Path,
    ) -> "LegalTechAPIClient":
        return cls(load_json(config_path), load_json(session_path))

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        remaining = self.delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        self._wait()
        response = self.session.post(
            url,
            json=body,
            timeout=self.timeout,
            allow_redirects=True,
        )
        self.last_request_at = time.monotonic()

        if response.status_code in {401, 403, 419}:
            raise LegalTechTokenError(
                f"Accès refusé ou token expiré (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            preview = response.text[:300].replace("\n", " ")
            raise LegalTechAPIError(
                f"HTTP {response.status_code} pour {url}: {preview!r}"
            )

        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise LegalTechAPIError(
                f"Réponse non JSON reçue depuis {url}."
            ) from exc

        if not isinstance(payload, dict):
            raise LegalTechAPIError("La réponse JSON doit être un objet.")
        return payload

    def fetch_articles(
        self,
        *,
        page: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[LegalTechArticle], dict[str, Any]]:
        if self.mode == "alert_results":
            request_body = dict(self.config.get("alert_request", {}))
            if page is not None:
                request_body["page"] = page
            if limit is not None:
                request_body["limit"] = limit
            payload = self._post_json(self.alert_results_url, request_body)

        elif self.mode == "article_search":
            request_body = dict(self.config.get("search_request", {}))
            if page is not None:
                request_body["page"] = page
            if limit is not None:
                request_body["size"] = limit
            payload = self._post_json(self.article_search_url, request_body)

        else:
            raise LegalTechConfigError(
                "mode doit être 'alert_results' ou 'article_search'."
            )

        return normalize_articles(payload, self.mode), payload

    def create_pdf_bytes(self, article: LegalTechArticle) -> bytes:
        article_payload = {
            "source": article.source,
            "title": article.title,
            "publishedAt": article.published_at,
            "articleText": article.article_text,
        }
        payload = self._post_json(
            self.pdf_url,
            {
                "article": article_payload,
                "token": self.pdf_token,
            },
        )
        return decode_pdf_base64(str(payload.get("pdf") or ""))

    def save_pdf(
        self,
        article: LegalTechArticle,
        target_dir: str | Path,
    ) -> SavedPDF:
        data = self.create_pdf_bytes(article)
        if len(data) > self.max_pdf_bytes:
            raise LegalTechAPIError(
                f"PDF trop volumineux : {len(data)} octets."
            )

        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        destination = target / article.filename
        partial = destination.with_suffix(destination.suffix + ".part")

        partial.write_bytes(data)
        partial.replace(destination)

        return SavedPDF(
            path=destination,
            sha256=sha256(data).hexdigest(),
            size_bytes=len(data),
        )
