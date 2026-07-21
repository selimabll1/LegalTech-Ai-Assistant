"""Tests hors ligne du collecteur LegalTech v2."""

from __future__ import annotations

import base64

from modules.legaltech_api_client_v2 import (
    LEGALTECH_API_CLIENT_VERSION,
    decode_pdf_base64,
    normalize_articles,
)


def main() -> None:
    fake_pdf = b"%PDF-1.4\n% test\n%%EOF\n"
    encoded = base64.b64encode(fake_pdf).decode("ascii")

    assert decode_pdf_base64(encoded) == fake_pdf
    assert (
        decode_pdf_base64(
            "data:application/pdf;base64," + encoded
        )
        == fake_pdf
    )

    payload = {
        "articles": [
            {
                "_id": "hit-1",
                "_source": {
                    "doc_id": "doc-1",
                    "title": "Annonce test",
                    "reference": "REF-001",
                    "lang": "fr",
                    "articleText": "Texte test",
                    "publishedAt": "2026-07-21T00:00:00Z",
                    "file": "test.pdf",
                    "source": "JORT",
                    "page": 3,
                },
            }
        ]
    }
    articles = normalize_articles(payload, "alert_results")
    assert len(articles) == 1
    assert articles[0].reference == "REF-001"
    assert articles[0].filename == "REF-001.pdf"
    assert articles[0].page == 3

    print("LEGALTECH COLLECTOR V2 — TEST HORS LIGNE OK")
    print("Client :", LEGALTECH_API_CLIENT_VERSION)
    print("Décodage Base64 PDF : OK")
    print("Normalisation article : OK")


if __name__ == "__main__":
    main()
