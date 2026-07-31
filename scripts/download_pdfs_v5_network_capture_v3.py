from __future__ import annotations

import argparse
import base64
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlparse

from modules.legaltech_browser_collector import LegalTechBrowserCollector
from modules.legaltech_notifications_collector import (
    DEFAULT_NOTIFICATIONS_URL,
    NotificationItem,
)
from modules.legaltech_notifications_network_collector import (
    NetworkFirstNotificationsCollector,
)

DB = Path("data/legaltech_notifications_v5.sqlite3")
OUT = Path("data/legaltech_pdfs")


def safe_name(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value or ""))
    value = re.sub(r"\s+", "_", value).strip(" ._")
    return value[:150] or "document"


def is_pdf_bytes(data: bytes) -> bool:
    return data.startswith(b"%PDF-")


def decode_pdf_from_json(value):
    if isinstance(value, dict):
        for key in ("pdf", "data", "document", "content", "file", "base64"):
            if key in value:
                found = decode_pdf_from_json(value[key])
                if found:
                    return found
        for child in value.values():
            found = decode_pdf_from_json(child)
            if found:
                return found
        return None

    if isinstance(value, list):
        for child in value:
            found = decode_pdf_from_json(child)
            if found:
                return found
        return None

    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("data:application/pdf;base64,"):
            candidate = candidate.split(",", 1)[1]

        if len(candidate) < 100:
            return None

        try:
            raw = base64.b64decode(candidate, validate=False)
        except Exception:
            return None

        if is_pdf_bytes(raw):
            return raw

    return None


def update_db(con, alert_key: str, status: str, path: Path | None):
    con.execute(
        """UPDATE notification_alerts
           SET download_status=?, download_path=?
           WHERE alert_key=?""",
        (status, str(path) if path else None, alert_key),
    )
    con.commit()


def load_rows(notification: str, limit: int):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    latest = con.execute(
        "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if not latest:
        con.close()
        raise SystemExit("Aucun run v5.")

    sql = """
        SELECT
            a.*,
            n.company_or_query,
            n.notification_date,
            n.announced_result_count,
            n.notification_page,
            n.raw_text AS notification_raw_text,
            n.notification_index
        FROM notification_alerts a
        JOIN notifications n
          ON n.notification_key = a.notification_key
        WHERE a.run_id=?
          AND a.detail_status='COLLECTED'
    """
    params = [latest["run_id"]]

    if notification:
        sql += " AND lower(n.company_or_query)=lower(?)"
        params.append(notification)

    sql += " ORDER BY n.notification_index, a.card_index, a.rowid"
    rows = con.execute(sql, params).fetchall()
    con.close()

    if limit > 0:
        rows = rows[:limit]
    return rows


def make_notif(row):
    return NotificationItem(
        notification_key=row["notification_key"],
        company_or_query=row["company_or_query"],
        notification_date=row["notification_date"] or "",
        announced_result_count=row["announced_result_count"],
        notification_page=int(row["notification_page"] or 1),
        raw_text=row["notification_raw_text"] or "",
        notification_index=int(row["notification_index"] or 0),
    )


def wait_for_cards(collector, timeout_seconds=15):
    """Wait until alert cards are actually rendered after notification click."""
    page = collector._page()
    deadline = time.time() + timeout_seconds
    last_count = 0
    last_see_more = 0

    while time.time() < deadline:
        try:
            last_see_more = collector._visible_see_more_count()
        except Exception:
            last_see_more = 0

        try:
            cards = collector._alert_cards()
            last_count = len(cards)
        except Exception:
            cards = []
            last_count = 0

        if last_count > 0:
            return cards, last_see_more

        page.wait_for_timeout(350)

    return [], last_see_more


def _card_matches_row(card, row) -> bool:
    text = str(card.get("text") or "").casefold()
    article_id = str(row["article_id"] or "").casefold()
    title = str(row["card_title"] or "").casefold()

    if article_id and article_id in text:
        return True
    if title and title in text:
        return True
    return False


def _panel_contains_target(cards, row) -> bool:
    return any(_card_matches_row(card, row) for card in cards)


def click_download_and_capture(browser, collector, row):
    """Use the normal UI flow and capture the PDF response.

    v3 important change:
    `_activate_notification()` returning False is NOT treated as a hard failure.
    LegalTech may already have the same notification selected, so the right
    panel fingerprint does not change even though the correct five cards are
    visible. We validate the actual rendered cards instead.
    """
    notif = make_notif(row)

    changed, _ = collector._activate_notification(notif, retries=2)
    print("  -> panel_changed:", changed)

    # Always inspect the panel, even when `changed == False`.
    cards, see_more_count = wait_for_cards(
        collector,
        timeout_seconds=15,
    )
    print(
        "  -> cartes visibles:",
        len(cards),
        "| voir_plus:",
        see_more_count,
    )

    target_visible = _panel_contains_target(cards, row)

    if cards and target_visible:
        print("  -> panneau validé par l'article cible")
    else:
        print(
            "  -> panneau non validé; "
            "réactivation contrôlée de la notification"
        )

        # One more activation attempt, then validate by CONTENT rather than
        # fingerprint alone.
        collector.browser.goto(DEFAULT_NOTIFICATIONS_URL)
        collector._wait_for_notification_items(
            max_notifications=10,
            timeout_seconds=20,
        )

        changed2, _ = collector._activate_notification(
            notif,
            retries=1,
        )
        print("  -> panel_changed retry:", changed2)

        cards, see_more_count = wait_for_cards(
            collector,
            timeout_seconds=15,
        )
        print(
            "  -> cartes après retry:",
            len(cards),
            "| voir_plus:",
            see_more_count,
        )

        target_visible = _panel_contains_target(cards, row)

    if not cards:
        return None, [], "CARDS_NOT_RENDERED_AFTER_WAIT"

    if not target_visible:
        # Print harmless visible card titles/ids to diagnose wrong panel,
        # never cookies/headers/request bodies.
        visible = []
        for card in cards[:8]:
            compact = re.sub(
                r"\s+",
                " ",
                str(card.get("text") or ""),
            ).strip()
            visible.append(compact[:160])
        print("  -> cartes vues:", visible)
        return None, [], "WRONG_NOTIFICATION_PANEL"

    # Prefer exact content matching over stored card_index.
    target_index = -1
    for card in cards:
        if _card_matches_row(card, row):
            target_index = int(card["index"])
            break

    if target_index < 0:
        return None, [], "CARD_MATCH_FAILED"

    page = browser._require_page()

    button = page.locator(
        f'[data-lt-download="{target_index}"]'
    ).first

    if button.count() == 0:
        card = page.locator(
            f'[data-lt-alert-card="{target_index}"]'
        ).first

        if card.count() > 0:
            # Search leaf-ish elements exactly named Télécharger.
            candidates = card.locator(
                'button,a,[role="button"],div,span'
            )
            for i in range(candidates.count()):
                candidate = candidates.nth(i)
                try:
                    txt = (candidate.inner_text(timeout=500) or "").strip()
                except Exception:
                    continue
                if re.fullmatch(
                    r"(Télécharger|Telecharger|Download)",
                    txt,
                    re.I,
                ):
                    button = candidate
                    break

    if button.count() == 0:
        return None, [], "DOWNLOAD_CONTROL_NOT_FOUND"

    events = []
    holder = {"bytes": None, "source": None}

    def on_response(response):
        try:
            request = response.request
            url = str(response.url)
            method = str(request.method or "GET").upper()
            status = int(response.status)

            try:
                ctype = response.headers.get("content-type", "")
            except Exception:
                ctype = ""

            path = urlparse(url).path

            interesting = (
                "pdf" in path.casefold()
                or "download" in path.casefold()
                or "document" in path.casefold()
                or "application/pdf" in ctype.casefold()
            )

            if interesting:
                events.append(
                    {
                        "method": method,
                        "path": path,
                        "status": status,
                        "content_type": ctype,
                    }
                )

            if status < 200 or status >= 300:
                return

            if "application/pdf" in ctype.casefold():
                try:
                    raw = response.body()
                    if is_pdf_bytes(raw):
                        holder["bytes"] = raw
                        holder["source"] = (
                            f"{method} {path} ({ctype})"
                        )
                        return
                except Exception:
                    pass

            if (
                "json" in ctype.casefold()
                or "pdf" in path.casefold()
            ):
                try:
                    raw = decode_pdf_from_json(response.json())
                    if raw:
                        holder["bytes"] = raw
                        holder["source"] = (
                            f"{method} {path} (JSON/Base64)"
                        )
                except Exception:
                    pass
        except Exception:
            pass

    page.on("response", on_response)

    try:
        meta = button.evaluate(
            """el => ({
                tag: el.tagName,
                text: (el.innerText || '').trim(),
                href: el.getAttribute('href'),
                role: el.getAttribute('role')
            })"""
        )
    except Exception:
        meta = {}

    print("  -> contrôle:", meta)

    try:
        button.scroll_into_view_if_needed()
        button.click(timeout=7000)
    except Exception as exc:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
        return None, events, f"CLICK_FAILED:{type(exc).__name__}"

    deadline = time.time() + 15
    while time.time() < deadline:
        if holder["bytes"]:
            break
        page.wait_for_timeout(250)

    try:
        page.remove_listener("response", on_response)
    except Exception:
        pass

    return holder["bytes"], events, holder["source"] or "NO_PDF_RESPONSE"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notification", default="VILAVI")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--delay", type=float, default=4.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if not DB.exists():
        raise SystemExit(f"Base introuvable: {DB}")

    rows = load_rows(args.notification, args.limit)
    if not rows:
        raise SystemExit("Aucune alerte correspondante.")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    ok = skipped = failed = 0

    with LegalTechBrowserCollector(
        headless=args.headless,
        slow_mo_ms=120 if not args.headless else 0,
    ) as browser:
        browser.ensure_authenticated(DEFAULT_NOTIFICATIONS_URL)

        # IMPORTANT: use the SAME collector class as the successful v5 sync.
        collector = NetworkFirstNotificationsCollector(browser)

        for i, row in enumerate(rows, 1):
            company = safe_name(row["company_or_query"])
            source = safe_name(row["source_label"] or row["source"])
            article = safe_name(
                row["article_id"]
                or row["card_title"]
                or row["alert_key"][:16]
            )

            folder = OUT / company
            folder.mkdir(parents=True, exist_ok=True)
            final_path = folder / f"{source}__{article}.pdf"

            if (
                not args.overwrite
                and row["download_status"] == "COLLECTED"
                and final_path.exists()
            ):
                print(f"[{i}/{len(rows)}] SKIP {row['card_title']}")
                skipped += 1
                continue

            print(
                f"[{i}/{len(rows)}] "
                f"{row['company_or_query']} · "
                f"{row['source_label'] or row['source']} · "
                f"{row['card_title'] or row['article_id']}"
            )

            pdf_bytes, events, result = click_download_and_capture(
                browser,
                collector,
                row,
            )

            for event in events:
                print(
                    "  -> réseau:",
                    event["method"],
                    event["path"],
                    "status=",
                    event["status"],
                    "type=",
                    event["content_type"] or "-",
                )

            if pdf_bytes:
                final_path.write_bytes(pdf_bytes)
                update_db(
                    con,
                    row["alert_key"],
                    "COLLECTED",
                    final_path,
                )
                print(
                    f"  -> PDF capturé ({len(pdf_bytes)} octets) via {result}"
                )
                print("  ->", final_path)
                ok += 1
            else:
                update_db(
                    con,
                    row["alert_key"],
                    "NOT_CAPTURED",
                    None,
                )
                print("  -> PDF non capturé:", result)
                failed += 1

            if i < len(rows):
                time.sleep(max(0.0, args.delay))

    con.close()

    print("\nPDF CAPTURE V3 TERMINÉ")
    print("collectés:", ok)
    print("déjà présents:", skipped)
    print("non capturés:", failed)
    print("dossier:", OUT)


if __name__ == "__main__":
    main()
