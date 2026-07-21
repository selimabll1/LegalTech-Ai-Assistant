"""Synchronise les PDF LegalTech observés dans une alerte ou une recherche."""

from __future__ import annotations

import argparse
from pathlib import Path

from modules.legaltech_api_client_v2 import (
    LEGALTECH_API_CLIENT_VERSION,
    LegalTechAPIClient,
)
from modules.legaltech_registry import LegalTechRegistry


SYNC_VERSION = "legaltech_sync_v2"


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
    parser.add_argument(
        "--target",
        type=Path,
        default=Path("data/pdf_raw"),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/legaltech_registry.sqlite3"),
    )
    parser.add_argument("--page", type=int, default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-items", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.limit < 1 or args.limit > 50:
        raise SystemExit("--limit doit être compris entre 1 et 50.")
    if args.max_items < 1 or args.max_items > 50:
        raise SystemExit("--max-items doit être compris entre 1 et 50.")

    client = LegalTechAPIClient.from_files(
        args.config,
        args.session,
    )
    registry = LegalTechRegistry(args.database)

    articles, _ = client.fetch_articles(
        page=args.page,
        limit=args.limit,
    )
    selected = articles[: args.max_items]

    print("Client :", LEGALTECH_API_CLIENT_VERSION)
    print("Synchronisation :", SYNC_VERSION)
    print("Mode :", client.mode)
    print("Articles reçus :", len(articles))
    print("Articles sélectionnés :", len(selected))

    collected = 0
    skipped = 0
    failed = 0

    for position, article in enumerate(selected, start=1):
        identifier = article.source_id or article.doc_id
        label = article.reference or article.title or identifier

        print(
            f"[{position}/{len(selected)}] "
            f"{label} · {article.source} · {article.published_at}"
        )

        if identifier and registry.has_source_id(identifier):
            print("  → déjà présent dans le registre")
            skipped += 1
            continue

        if args.dry_run:
            print(
                f"  → test seulement; PDF prévu : "
                f"{args.target / article.filename}"
            )
            continue

        try:
            saved = client.save_pdf(article, args.target)
            inserted = registry.register(
                source_id=identifier or None,
                reference=article.reference or None,
                source_url=None,
                download_url=client.pdf_url,
                filename=saved.path.name,
                local_path=saved.path,
                sha256=saved.sha256,
                size_bytes=saved.size_bytes,
                published_at=article.published_at or None,
                metadata={
                    "title": article.title,
                    "language": article.language,
                    "source": article.source,
                    "file": article.file,
                    "page": article.page,
                    "doc_id": article.doc_id,
                },
            )

            if inserted:
                collected += 1
                print(
                    f"  → collecté : {saved.path} "
                    f"({saved.size_bytes} octets)"
                )
            else:
                saved.path.unlink(missing_ok=True)
                skipped += 1
                print("  → doublon SHA-256, fichier supprimé")
        except Exception as exc:
            failed += 1
            print(f"  → ÉCHEC : {exc}")

    print("---")
    print("Collectés :", collected)
    print("Déjà connus :", skipped)
    print("Échecs :", failed)
    if args.dry_run:
        print("Mode test : aucun PDF n'a été généré.")


if __name__ == "__main__":
    main()
