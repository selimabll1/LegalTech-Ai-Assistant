"""Test en lecture seule de l'accès aux articles LegalTech."""

from __future__ import annotations

import argparse
from pathlib import Path

from modules.legaltech_api_client_v2 import (
    LEGALTECH_API_CLIENT_VERSION,
    LegalTechAPIClient,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/legaltech_collection.local.json"),
    )
    parser.add_argument(
        "--session",
        type=Path,
        default=Path("secrets/legaltech_session.local.json"),
    )
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    client = LegalTechAPIClient.from_files(
        args.config,
        args.session,
    )
    articles, _ = client.fetch_articles(limit=args.limit)

    print("ACCÈS AUX ARTICLES LEGALTECH OK")
    print("Client :", LEGALTECH_API_CLIENT_VERSION)
    print("Mode :", client.mode)
    print("Articles reçus :", len(articles))

    for index, article in enumerate(articles[:3], start=1):
        print(
            f"{index}. référence={article.reference or '-'} "
            f"source={article.source or '-'} "
            f"langue={article.language or '-'} "
            f"date={article.published_at or '-'} "
            f"caractères={len(article.article_text)}"
        )

    print("Aucun PDF n'a été généré par ce test.")


if __name__ == "__main__":
    main()
