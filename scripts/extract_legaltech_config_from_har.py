"""Extrait localement la configuration LegalTech depuis un HAR privé.

Le script :
- lit le token utilisé par /api/pdfNewsPapers ;
- lit la requête d'alerte ou de recherche capturée ;
- écrit les fichiers locaux de configuration ;
- ne montre jamais le token dans la console.

Le HAR original et les fichiers générés doivent rester hors Git.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


EXTRACTOR_VERSION = "legaltech_local_config_extractor_v1"


def read_har(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = payload.get("log", {}).get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("HAR invalide : log.entries absent.")
    return [entry for entry in entries if isinstance(entry, dict)]


def post_json(entry: dict[str, Any]) -> dict[str, Any] | None:
    request = entry.get("request", {}) or {}
    post_data = request.get("postData", {}) or {}
    text = post_data.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def path_of(entry: dict[str, Any]) -> str:
    request = entry.get("request", {}) or {}
    return urlsplit(str(request.get("url", ""))).path


def latest_matching(
    entries: list[dict[str, Any]],
    path: str,
    method: str = "POST",
) -> tuple[dict[str, Any], dict[str, Any]]:
    for entry in reversed(entries):
        request = entry.get("request", {}) or {}
        if (
            str(request.get("method", "")).upper() == method
            and path_of(entry) == path
        ):
            body = post_json(entry)
            if body is not None:
                return entry, body
    raise ValueError(f"Requête introuvable dans le HAR : {method} {path}")


def optional_matching(
    entries: list[dict[str, Any]],
    path: str,
    method: str = "POST",
) -> dict[str, Any] | None:
    try:
        _, body = latest_matching(entries, path, method)
        return body
    except ValueError:
        return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("har", type=Path)
    parser.add_argument(
        "--config-output",
        type=Path,
        default=Path("config/legaltech_collection.local.json"),
    )
    parser.add_argument(
        "--secret-output",
        type=Path,
        default=Path("secrets/legaltech_session.local.json"),
    )
    parser.add_argument(
        "--prefer",
        choices=("alert_results", "article_search"),
        default="alert_results",
    )
    args = parser.parse_args()

    entries = read_har(args.har)

    _, pdf_body = latest_matching(
        entries,
        "/api/pdfNewsPapers",
    )
    token = str(pdf_body.get("token") or "").strip()
    if not token:
        raise SystemExit(
            "Token absent de la requête /api/pdfNewsPapers."
        )

    alert_body = optional_matching(
        entries,
        "/api/secure/request/result",
    )
    search_body = optional_matching(
        entries,
        "/api/secure/article/list",
    )

    if args.prefer == "alert_results" and alert_body:
        mode = "alert_results"
    elif search_body:
        mode = "article_search"
    elif alert_body:
        mode = "alert_results"
    else:
        raise SystemExit(
            "Aucune requête d'alerte ou de recherche exploitable."
        )

    config = {
        "collector_version": "legaltech_collector_v2",
        "mode": mode,
        "api_base_url": "https://annoncesbo.legaltech.tn",
        "frontend_base_url": "https://annonces.legaltech.tn",
        "endpoints": {
            "alert_results": (
                "https://annoncesbo.legaltech.tn"
                "/api/secure/request/result"
            ),
            "article_search": (
                "https://annoncesbo.legaltech.tn"
                "/api/secure/article/list"
            ),
            "pdf_generation": (
                "https://annonces.legaltech.tn"
                "/api/pdfNewsPapers"
            ),
        },
        "alert_request": alert_body or {},
        "search_request": search_body or {},
        "timeout_seconds": 60,
        "min_delay_seconds": 1.5,
        "max_pdf_mb": 100,
    }

    secret = {
        "_warning": (
            "Secret local. Ne jamais versionner ni partager ce fichier."
        ),
        "pdf_token": token,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_har": args.har.name,
    }

    write_json(args.config_output, config)
    write_json(args.secret_output, secret)

    print("CONFIGURATION LEGALTECH LOCALE CRÉÉE")
    print("Extracteur :", EXTRACTOR_VERSION)
    print("Mode :", mode)
    print("Configuration :", args.config_output)
    print("Secret :", args.secret_output)
    print("Le token n'a pas été affiché.")
    print("Ces deux fichiers doivent rester hors Git.")


if __name__ == "__main__":
    main()
