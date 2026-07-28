
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid
from typing import Any

from modules.legaltech_browser_collector import (
    AuthenticationRequired,
    BrowserResult,
    DEFAULT_BASE_URL,
    LegalTechBrowserCollector,
    normalize_space,
    parse_article_url,
)

LEGALTECH_NOTIFICATIONS_COLLECTOR_VERSION = "legaltech_notifications_collector_v4_6_robust_dom_fix"
DEFAULT_NOTIFICATIONS_URL = f"{DEFAULT_BASE_URL}/page-notifications"
DEFAULT_NOTIFICATIONS_DB = Path("data/legaltech_notifications_v4.sqlite3")

DATE_RX = re.compile(r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b")
COUNT_RX = re.compile(
    r"(?P<count>\d+)\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour\s+",
    re.I,
)
PANEL_TOTAL_RX = re.compile(
    r"Afficher\s+\d+\s+de\s+(?P<total>\d+)\s+r[ée]sultats?",
    re.I,
)

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def stable_hash(*parts):
    return sha256(
        "|".join(str(x or "") for x in parts).encode("utf-8")
    ).hexdigest()

@dataclass(frozen=True)
class NotificationItem:
    notification_key: str
    company_or_query: str
    notification_date: str
    announced_result_count: int | None
    notification_page: int
    raw_text: str
    notification_index: int = 0

@dataclass(frozen=True)
class NotificationAlert:
    alert_key: str
    notification_key: str
    source: str
    source_label: str
    article_id: str
    doc_id: str
    article_url: str
    alert_page: int
    card_text: str
    card_date: str
    card_title: str
    card_summary: str
    notification_index: int = 0
    card_index: int = 0

@dataclass(frozen=True)
class SyncSummary:
    run_id: str
    notifications_found: int
    notifications_loaded: int
    notifications_failed: int
    alerts_found: int
    details_ok: int
    details_failed: int
    downloads_ok: int
    downloads_failed: int

class NotificationsRegistry:
    def __init__(self, path: str | Path = DEFAULT_NOTIFICATIONS_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    message TEXT
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    notification_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    company_or_query TEXT NOT NULL,
                    notification_date TEXT,
                    announced_result_count INTEGER,
                    panel_total INTEGER,
                    notification_page INTEGER,
                    load_status TEXT NOT NULL,
                    load_error TEXT,
                    raw_text TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notification_alerts (
                    alert_key TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    notification_key TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_label TEXT NOT NULL DEFAULT '',
                    article_id TEXT NOT NULL,
                    doc_id TEXT,
                    article_url TEXT NOT NULL,
                    alert_page INTEGER,
                    card_text TEXT NOT NULL DEFAULT '',
                    card_date TEXT NOT NULL DEFAULT '',
                    card_title TEXT NOT NULL DEFAULT '',
                    card_summary TEXT NOT NULL DEFAULT '',
                    detail_title TEXT NOT NULL DEFAULT '',
                    detail_text TEXT NOT NULL DEFAULT '',
                    source_fields_json TEXT NOT NULL DEFAULT '{}',
                    detail_status TEXT NOT NULL DEFAULT 'NOT_FETCHED',
                    detail_error TEXT,
                    download_status TEXT NOT NULL DEFAULT 'NOT_REQUESTED',
                    download_path TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );
                """
            )

            notification_columns = {
                row[1]
                for row in con.execute(
                    "PRAGMA table_info(notifications)"
                ).fetchall()
            }
            if "notification_index" not in notification_columns:
                con.execute(
                    "ALTER TABLE notifications "
                    "ADD COLUMN notification_index INTEGER NOT NULL DEFAULT 0"
                )

            alert_columns = {
                row[1]
                for row in con.execute(
                    "PRAGMA table_info(notification_alerts)"
                ).fetchall()
            }
            for column, sql_type in {
                "notification_index": "INTEGER NOT NULL DEFAULT 0",
                "card_index": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if column not in alert_columns:
                    con.execute(
                        f"ALTER TABLE notification_alerts "
                        f"ADD COLUMN {column} {sql_type}"
                    )

    @contextmanager
    def _connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def start_run(self):
        run_id = uuid.uuid4().hex
        with self._connect() as con:
            con.execute(
                "INSERT INTO runs VALUES (?, ?, NULL, 'RUNNING', NULL)",
                (run_id, utc_now()),
            )
        return run_id

    def finish_run(self, run_id, status, message=""):
        with self._connect() as con:
            con.execute(
                """UPDATE runs
                   SET finished_at=?, status=?, message=?
                   WHERE run_id=?""",
                (utc_now(), status, message[:2000], run_id),
            )

    def upsert_notification(
        self,
        run_id: str,
        x: NotificationItem,
        *,
        load_status="PENDING",
        load_error="",
        panel_total=None,
    ):
        now = utc_now()
        with self._connect() as con:
            row = con.execute(
                "SELECT first_seen_at FROM notifications WHERE notification_key=?",
                (x.notification_key,),
            ).fetchone()
            first_seen = row["first_seen_at"] if row else now

            con.execute(
                """INSERT INTO notifications (
                       notification_key, run_id, company_or_query,
                       notification_date, announced_result_count, panel_total,
                       notification_page, load_status, load_error, raw_text,
                       first_seen_at, last_seen_at, notification_index
                   )
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(notification_key) DO UPDATE SET
                       run_id=excluded.run_id,
                       company_or_query=excluded.company_or_query,
                       notification_date=excluded.notification_date,
                       announced_result_count=excluded.announced_result_count,
                       panel_total=excluded.panel_total,
                       notification_page=excluded.notification_page,
                       load_status=excluded.load_status,
                       load_error=excluded.load_error,
                       raw_text=excluded.raw_text,
                       last_seen_at=excluded.last_seen_at,
                       notification_index=excluded.notification_index""",
                (
                    x.notification_key, run_id, x.company_or_query,
                    x.notification_date, x.announced_result_count, panel_total,
                    x.notification_page, load_status, load_error, x.raw_text,
                    first_seen, now, x.notification_index,
                ),
            )

    def update_notification_load(
        self, key, *, status, error="", panel_total=None
    ):
        with self._connect() as con:
            con.execute(
                """UPDATE notifications
                   SET load_status=?, load_error=?, panel_total=?, last_seen_at=?
                   WHERE notification_key=?""",
                (status, error[:2000], panel_total, utc_now(), key),
            )

    def upsert_alert(self, run_id, x: NotificationAlert):
        now = utc_now()
        with self._connect() as con:
            row = con.execute(
                "SELECT first_seen_at FROM notification_alerts WHERE alert_key=?",
                (x.alert_key,),
            ).fetchone()
            first_seen = row["first_seen_at"] if row else now
            con.execute(
                """INSERT INTO notification_alerts (
                       alert_key, run_id, notification_key, source, source_label,
                       article_id, doc_id, article_url, alert_page,
                       card_text, card_date, card_title, card_summary,
                       first_seen_at, last_seen_at,
                       notification_index, card_index
                   )
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(alert_key) DO UPDATE SET
                       run_id=excluded.run_id,
                       notification_key=excluded.notification_key,
                       source=excluded.source,
                       source_label=excluded.source_label,
                       article_id=excluded.article_id,
                       doc_id=excluded.doc_id,
                       article_url=excluded.article_url,
                       alert_page=excluded.alert_page,
                       card_text=excluded.card_text,
                       card_date=excluded.card_date,
                       card_title=excluded.card_title,
                       card_summary=excluded.card_summary,
                       last_seen_at=excluded.last_seen_at,
                       notification_index=excluded.notification_index,
                       card_index=excluded.card_index""",
                (
                    x.alert_key, run_id, x.notification_key, x.source,
                    x.source_label, x.article_id, x.doc_id, x.article_url,
                    x.alert_page, x.card_text, x.card_date, x.card_title,
                    x.card_summary, first_seen, now,
                    x.notification_index, x.card_index,
                ),
            )

    def save_detail(self, alert_key, title, text, fields):
        with self._connect() as con:
            con.execute(
                """UPDATE notification_alerts
                   SET detail_title=?, detail_text=?, source_fields_json=?,
                       detail_status='COLLECTED', detail_error=NULL,
                       last_seen_at=?
                   WHERE alert_key=?""",
                (
                    title, text,
                    json.dumps(fields, ensure_ascii=False, sort_keys=True),
                    utc_now(), alert_key,
                ),
            )

    def update_alert_route(
        self,
        alert_key,
        *,
        source=None,
        article_id=None,
        doc_id=None,
        article_url=None,
    ):
        updates = []
        values = []

        for column, value in (
            ("source", source),
            ("article_id", article_id),
            ("doc_id", doc_id),
            ("article_url", article_url),
        ):
            if value not in (None, ""):
                updates.append(f"{column}=?")
                values.append(value)

        if not updates:
            return

        updates.append("last_seen_at=?")
        values.append(utc_now())
        values.append(alert_key)

        with self._connect() as con:
            con.execute(
                f"UPDATE notification_alerts "
                f"SET {', '.join(updates)} WHERE alert_key=?",
                tuple(values),
            )

    def mark_detail_failed(self, alert_key, error):
        with self._connect() as con:
            con.execute(
                """UPDATE notification_alerts
                   SET detail_status='FAILED', detail_error=?, last_seen_at=?
                   WHERE alert_key=?""",
                (str(error)[:2000], utc_now(), alert_key),
            )

    def mark_download(self, alert_key, status, path=None):
        with self._connect() as con:
            con.execute(
                """UPDATE notification_alerts
                   SET download_status=?, download_path=?, last_seen_at=?
                   WHERE alert_key=?""",
                (status, str(path) if path else None, utc_now(), alert_key),
            )

class LegalTechNotificationsCollector:
    def __init__(self, browser: LegalTechBrowserCollector):
        self.browser = browser
        self.registry = NotificationsRegistry()

    def _page(self):
        return self.browser._require_page()

    def install_read_state_guard(self):
        page = self._page()

        def guard(route, request):
            url = str(request.url or "")
            if "/api/secure/notification/" in url:
                print(
                    "[SAFE] readNotification neutralisé:",
                    request.method,
                    url,
                )
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body="{}",
                )
                return
            route.continue_()

        page.route("**/*", guard)

    def _notification_candidates(self):
        """Find individual notification cards robustly.

        v4.2 was too strict: it required a compact element that already
        contained both the notification phrase and its date. On LegalTech,
        the count/company text and date can live in sibling elements, so that
        produced 0 cards.

        v4.3 starts from the smallest text element containing exactly one
        notification phrase, then climbs only until it reaches the smallest
        left-column ancestor that also contains one date. It rejects ancestors
        containing multiple notification phrases, so it cannot become the
        whole notification-list container.
        """
        page = self._page()

        # The page can render the shell before the notification list appears.
        try:
            page.wait_for_function(
                r"""() => {
                    const text = document.body?.innerText || '';
                    return /\d+\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour/i.test(text);
                }""",
                timeout=15000,
            )
        except Exception:
            pass

        return page.locator("body").evaluate(
            r"""root => {
                const phraseSource =
                    String.raw`\d+\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour`;
                const phraseOne = new RegExp(phraseSource, 'i');
                const phraseAll = new RegExp(phraseSource, 'ig');
                const dateAll = /\b\d{2}-\d{2}-\d{4}\b/g;
                const vw = window.innerWidth || 1500;

                // Clear old tags.
                for (const old of root.querySelectorAll('[data-lt-notification-card]')) {
                    old.removeAttribute('data-lt-notification-card');
                }

                // Start from the smallest/leaf-most elements containing the phrase.
                const seeds = [];
                for (const el of root.querySelectorAll('*')) {
                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) continue;
                    if (r.left >= vw * 0.48) continue;

                    const text = (el.innerText || '').trim();
                    if (!phraseOne.test(text)) continue;

                    const matches = text.match(phraseAll) || [];
                    if (matches.length !== 1) continue;

                    // Prefer elements whose children do not themselves contain
                    // the notification phrase.
                    const childContainsPhrase = [...el.children].some(ch =>
                        phraseOne.test((ch.innerText || '').trim())
                    );
                    if (!childContainsPhrase) {
                        seeds.push(el);
                    }
                }

                const cards = [];

                for (const seed of seeds) {
                    let node = seed;
                    let fallback = seed;
                    let chosen = null;

                    for (let depth = 0; depth < 8 && node; depth++, node = node.parentElement) {
                        const r = node.getBoundingClientRect();
                        const text = (node.innerText || '').trim();

                        if (!r.width || !r.height) continue;
                        if (r.left >= vw * 0.48) break;
                        if (r.width > vw * 0.48) break;
                        if (r.height > 260) break;

                        const phrases = text.match(phraseAll) || [];
                        if (phrases.length !== 1) break;

                        fallback = node;

                        const dates = text.match(dateAll) || [];
                        if (dates.length >= 1) {
                            chosen = node;
                            break;
                        }
                    }

                    const card = chosen || fallback;
                    if (!card) continue;

                    const r = card.getBoundingClientRect();
                    const text = (card.innerText || '').trim();
                    if (!text) continue;
                    if (/Sélectionnez une notification/i.test(text)) continue;

                    const phrases = text.match(phraseAll) || [];
                    if (phrases.length !== 1) continue;

                    cards.push({
                        el: card,
                        text,
                        x: r.left,
                        y: r.top,
                        width: r.width,
                        height: r.height,
                        area: r.width * r.height
                    });
                }

                cards.sort((a,b) => a.y-b.y || a.area-b.area);

                const unique = [];
                for (const row of cards) {
                    const compact = row.text.replace(/\s+/g, ' ').trim();
                    const duplicate = unique.some(prev => {
                        const prevCompact =
                            prev.text.replace(/\s+/g, ' ').trim();
                        return (
                            compact === prevCompact ||
                            (
                                Math.abs(prev.y-row.y) < 10 &&
                                Math.abs(prev.x-row.x) < 10
                            )
                        );
                    });
                    if (!duplicate) unique.push(row);
                }

                unique.forEach((row, index) => {
                    row.el.setAttribute(
                        'data-lt-notification-card',
                        String(index)
                    );
                });

                return unique.map((row, index) => ({
                    index,
                    text: row.text,
                    x: row.x,
                    y: row.y,
                    width: row.width,
                    height: row.height
                }));
            }"""
        )

    def _parse_notification(self, text, page_no, notification_index=0):
        compact = normalize_space(text)
        cm = COUNT_RX.search(compact)
        count = int(cm.group("count")) if cm else None
        dm = DATE_RX.search(compact)
        date = dm.group(1) if dm else ""

        company = compact[cm.end():].strip() if cm else compact
        if date:
            company = company.replace(date, "").strip()
        company = re.sub(r"\s+", " ", company).strip(" -")

        return NotificationItem(
            notification_key=stable_hash(company.casefold(), date, compact),
            company_or_query=company,
            notification_date=date,
            announced_result_count=count,
            notification_page=page_no,
            raw_text=compact,
            notification_index=notification_index,
        )

    def _tag_notification_target(self, notif: NotificationItem) -> int:
        """Tag the exact notification card and a few ancestors.

        We match by BOTH company text and date, instead of relying on an index
        after React re-renders. This avoids clicking the wrong element when the
        DOM changes after selecting CENTRAL/VILAVI/etc.
        """
        page = self._page()

        for old in page.locator(
            "[data-lt-notification-target-depth]"
        ).all():
            try:
                old.remove_attribute("data-lt-notification-target-depth")
            except Exception:
                pass

        result = page.locator("body").evaluate(
            r"""(root, args) => {
                const company = (args.company || '').trim().toLowerCase();
                const date = (args.date || '').trim();
                const phraseRx =
                    /\d+\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour/i;
                const vw = window.innerWidth || 1500;

                const cards = [...root.querySelectorAll('*')].filter(el => {
                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) return false;
                    if (r.left >= vw * 0.48) return false;

                    const text = (el.innerText || '').trim();
                    if (!phraseRx.test(text)) return false;

                    const lower = text.toLowerCase();
                    if (company && !lower.includes(company)) return false;
                    if (date && !text.includes(date)) return false;

                    const phrases = text.match(
                        /\d+\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour/ig
                    ) || [];
                    if (phrases.length !== 1) return false;

                    return true;
                });

                if (!cards.length) return 0;

                // Pick the smallest matching visible element.
                cards.sort((a, b) => {
                    const ar = a.getBoundingClientRect();
                    const br = b.getBoundingClientRect();
                    return (ar.width * ar.height) - (br.width * br.height);
                });

                let node = cards[0];
                let depth = 0;
                let tagged = 0;

                while (node && depth < 7) {
                    const r = node.getBoundingClientRect();
                    const text = (node.innerText || '').trim();

                    if (!r.width || !r.height) break;
                    if (r.left >= vw * 0.48) break;

                    const phrases = text.match(
                        /\d+\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour/ig
                    ) || [];
                    if (phrases.length !== 1) break;

                    node.setAttribute(
                        'data-lt-notification-target-depth',
                        String(depth)
                    );
                    tagged++;
                    depth++;
                    node = node.parentElement;
                }

                return tagged;
            }""",
            {
                "company": notif.company_or_query,
                "date": notif.notification_date,
            },
        )

        return int(result or 0)

    def _click_notification_candidate(
        self,
        notif: NotificationItem,
        depth: int,
    ) -> None:
        """Click one tagged notification element/ancestor."""
        page = self._page()
        locator = page.locator(
            f'[data-lt-notification-target-depth="{depth}"]'
        ).first

        if locator.count() == 0:
            raise RuntimeError(
                f"Cible notification profondeur {depth} introuvable."
            )

        locator.scroll_into_view_if_needed()

        # Normal click first. If the website overlays the inner card, fall back
        # to a DOM click, which still triggers the site's click handler/bubbling.
        try:
            locator.click(timeout=4000)
        except Exception:
            locator.evaluate("(el) => el.click()")

        page.wait_for_timeout(900)

    def _click_notification(self, index):
        """Compatibility wrapper for older scripts.

        New code should use _activate_notification(notif), which matches by
        company/date and tries the card + ancestors.
        """
        rows = self._notification_candidates()
        if index < 0 or index >= len(rows):
            raise RuntimeError(
                f"Notification index {index} introuvable "
                f"(cartes détectées: {len(rows)})"
            )

        notif = self._parse_notification(
            rows[index]["text"],
            1,
            notification_index=index,
        )
        tagged = self._tag_notification_target(notif)
        if tagged == 0:
            raise RuntimeError(
                f"Notification {notif.company_or_query} introuvable."
            )
        self._click_notification_candidate(notif, 0)

    def _visible_see_more_count(self):
        return self._page().locator("body").evaluate(
            r"""root => {
                const vw = window.innerWidth || 1500;
                let count = 0;

                for (const el of root.querySelectorAll(
                    'button,a,[role="button"],div,span'
                )) {
                    const text = (el.innerText || '').trim();
                    if (!/^Voir\s*plus$/i.test(text)) continue;

                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) continue;
                    if (r.left < vw * 0.48) continue;

                    // Keep only leaf-ish controls, not parent containers.
                    const childSame = [...el.children].some(ch =>
                        /^Voir\s*plus$/i.test(
                            (ch.innerText || '').trim()
                        )
                    );
                    if (childSame) continue;

                    count++;
                }
                return count;
            }"""
        )

    def _right_panel_snapshot(self):
        """Visible text in the right half, collected from text nodes.

        This avoids giant duplicated ancestor innerText blocks and gives a
        reliable fingerprint when the selected notification changes.
        """
        return self._page().locator("body").evaluate(
            r"""root => {
                const vw = window.innerWidth || 1500;
                const walker = document.createTreeWalker(
                    root,
                    NodeFilter.SHOW_TEXT
                );
                const parts = [];
                let node;

                while ((node = walker.nextNode())) {
                    const text = (node.nodeValue || '').replace(/\s+/g,' ').trim();
                    if (!text) continue;

                    const parent = node.parentElement;
                    if (!parent) continue;

                    const style = window.getComputedStyle(parent);
                    if (
                        style.display === 'none' ||
                        style.visibility === 'hidden' ||
                        Number(style.opacity || '1') === 0
                    ) continue;

                    const r = parent.getBoundingClientRect();
                    if (!r.width || !r.height) continue;

                    const centerX = r.left + r.width / 2;
                    if (centerX < vw * 0.50) continue;

                    parts.push(text);
                }

                return parts.join('\n').slice(0, 50000);
            }"""
        )

    def _right_state_fingerprint(self):
        return stable_hash(
            self._visible_see_more_count(),
            self._right_panel_snapshot(),
        )

    def _wait_panel_change(self, before_fingerprint, timeout=12):
        page = self._page()
        deadline = time.time() + timeout

        while time.time() < deadline:
            current_fp = self._right_state_fingerprint()
            count = self._visible_see_more_count()
            panel = self._right_panel_snapshot()

            if (
                current_fp != before_fingerprint
                and (
                    count > 0
                    or "Liste des alertes" in panel
                    or "Aucun" in panel
                )
            ):
                return True, panel

            page.wait_for_timeout(300)

        return False, self._right_panel_snapshot()

    def _panel_total(self):
        text = self._right_panel_snapshot()
        m = PANEL_TOTAL_RX.search(text)
        return int(m.group("total")) if m else None

    def _alert_cards(self):
        """Extract one full card per visible 'Voir plus'.

        v4.5 saw five Voir plus controls but zero cards because the ancestor
        geometry filters were too restrictive for LegalTech's actual layout.

        v4.6 simply climbs from each Voir plus control while the ancestor still
        contains exactly ONE Voir plus. The largest such ancestor is the card.
        """
        return self._page().locator("body").evaluate(
            r"""root => {
                for (const old of root.querySelectorAll(
                    '[data-lt-alert-card],[data-lt-see-more],[data-lt-download]'
                )) {
                    old.removeAttribute('data-lt-alert-card');
                    old.removeAttribute('data-lt-see-more');
                    old.removeAttribute('data-lt-download');
                }

                const vw = window.innerWidth || 1500;

                // Find the smallest elements representing the five visible
                // "Voir plus" controls.
                const rawControls = [...root.querySelectorAll(
                    'button,a,[role="button"],div,span'
                )].filter(el => {
                    const text = (el.innerText || '').trim();
                    if (!/^Voir\s*plus$/i.test(text)) return false;

                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) return false;
                    if (r.left < vw * 0.48) return false;

                    const childSame = [...el.children].some(ch =>
                        /^Voir\s*plus$/i.test(
                            (ch.innerText || '').trim()
                        )
                    );
                    return !childSame;
                });

                const rows = [];

                for (const control of rawControls) {
                    let node = control;
                    let best = null;

                    for (
                        let depth = 0;
                        depth < 18 && node;
                        depth++, node = node.parentElement
                    ) {
                        const text = (node.innerText || '').trim();
                        if (!text) continue;

                        const seeMoreDesc = [
                            ...node.querySelectorAll(
                                'button,a,[role="button"],div,span'
                            )
                        ].filter(x => {
                            const t = (x.innerText || '').trim();
                            if (!/^Voir\s*plus$/i.test(t)) return false;

                            const childSame = [...x.children].some(ch =>
                                /^Voir\s*plus$/i.test(
                                    (ch.innerText || '').trim()
                                )
                            );
                            return !childSame;
                        }).length;

                        if (seeMoreDesc > 1) {
                            break;
                        }

                        if (seeMoreDesc === 1) {
                            // Keep climbing: the largest ancestor that still
                            // contains exactly one Voir plus is the best card.
                            best = node;
                        }
                    }

                    if (!best) {
                        best = control.parentElement || control;
                    }

                    const text = (best.innerText || '').trim();
                    rows.push({
                        el: best,
                        control,
                        text,
                        top: best.getBoundingClientRect().top
                    });
                }

                rows.sort((a,b) => a.top - b.top);

                // Deduplicate by control position/text; keep all five cards
                // even when two cards have similar content.
                const unique = [];
                for (const row of rows) {
                    const controlRect = row.control.getBoundingClientRect();
                    const key =
                        Math.round(controlRect.top) + '|' +
                        Math.round(controlRect.left);
                    if (unique.some(x => x.key === key)) continue;
                    unique.push({...row, key});
                }

                return unique.map((row, index) => {
                    row.el.setAttribute(
                        'data-lt-alert-card',
                        String(index)
                    );
                    row.control.setAttribute(
                        'data-lt-see-more',
                        String(index)
                    );

                    // Find a visible Télécharger sibling/descendant if present.
                    const descendants = [...row.el.querySelectorAll(
                        'button,a,[role="button"],div,span'
                    )];

                    const download = descendants.find(x => {
                        const t = (x.innerText || '').trim();
                        if (!/^(Télécharger|Telecharger|Download)$/i.test(t)) {
                            return false;
                        }
                        const childSame = [...x.children].some(ch =>
                            /^(Télécharger|Telecharger|Download)$/i.test(
                                (ch.innerText || '').trim()
                            )
                        );
                        return !childSame;
                    });

                    if (download) {
                        download.setAttribute(
                            'data-lt-download',
                            String(index)
                        );
                    }

                    const articleLink =
                        row.el.querySelector('a[href*="/article/"]');

                    return {
                        index,
                        href: articleLink
                            ? (
                                articleLink.href ||
                                articleLink.getAttribute('href') ||
                                ''
                              )
                            : '',
                        text: row.text,
                        top: row.top
                    };
                });
            }"""
        )

    @staticmethod
    def _parse_card(text, fallback_company, source):
        lines = [
            normalize_space(x)
            for x in str(text or "").splitlines()
            if normalize_space(x)
        ]
        clean = []
        for line in lines:
            low = line.casefold()
            if low in {"télécharger", "telecharger", "voir plus"}:
                continue
            clean.append(line)

        date = ""
        date_index = None
        for i, line in enumerate(clean):
            m = DATE_RX.search(line)
            if m:
                date = m.group(1)
                date_index = i
                break

        source_label = clean[0] if clean else source

        title = ""
        start = (date_index + 1) if date_index is not None else 1
        for line in clean[start:]:
            if len(line) < 6:
                continue
            title = line
            break

        if not title and len(clean) > 1:
            title = clean[1]

        summary_parts = []
        title_seen = False
        for line in clean:
            if title and line == title:
                title_seen = True
                continue
            if not title_seen:
                continue
            if date and date in line:
                continue
            summary_parts.append(line)

        summary = " ".join(summary_parts).strip()

        return {
            "source_label": source_label,
            "card_date": date,
            "card_title": title,
            "card_summary": summary,
        }

    @staticmethod
    def _infer_source(source_label: str) -> str:
        value = normalize_space(source_label).casefold()

        if "registre national" in value or value == "rne":
            return "rne"
        if "jort" in value or "journal officiel" in value:
            return "jort"
        if "chourouk" in value:
            return "JrChourouk"
        if "quotidien" in value:
            return "JrLeQuotidien"
        if "temps" in value:
            return "JrLeTemps"
        if "assabeh" in value or "sabah" in value:
            return "JrAssabeh"
        if "presse" in value:
            return "JrLaPress"

        # Keep a stable readable fallback.
        compact = re.sub(r"[^A-Za-z0-9]+", "", source_label)
        return compact or "unknown"

    def _current_alerts(self, notif, alert_page):
        out = {}

        for raw in self._alert_cards():
            raw_text = raw.get("text") or ""
            href = str(raw.get("href") or "").strip()
            card_index = int(raw.get("index") or 0)

            # Parse the visible card even when LegalTech exposes no href.
            provisional_source = ""
            provisional_fields = self._parse_card(
                raw_text,
                notif.company_or_query,
                "unknown",
            )
            provisional_source = self._infer_source(
                provisional_fields["source_label"]
            )

            article_id = (
                f"card-{notif.notification_key[:10]}-"
                f"{alert_page}-{card_index}"
            )
            doc_id = ""
            article_url = ""
            source = provisional_source

            if href:
                try:
                    parsed = parse_article_url(
                        href,
                        self.browser.base_url,
                    )
                    source = parsed.source
                    article_id = parsed.article_id
                    doc_id = parsed.doc_id
                    article_url = parsed.article_url
                except ValueError:
                    article_url = href

            fields = self._parse_card(
                raw_text,
                notif.company_or_query,
                source,
            )

            key = stable_hash(
                notif.notification_key,
                alert_page,
                card_index,
                normalize_space(raw_text),
            )

            out[key] = NotificationAlert(
                alert_key=key,
                notification_key=notif.notification_key,
                source=source,
                source_label=fields["source_label"],
                article_id=article_id,
                doc_id=doc_id,
                article_url=article_url,
                alert_page=alert_page,
                card_text=normalize_space(raw_text),
                card_date=fields["card_date"],
                card_title=fields["card_title"],
                card_summary=fields["card_summary"],
                notification_index=notif.notification_index,
                card_index=card_index,
            )

        return list(out.values())

    def _article_fingerprint(self):
        cards = self._alert_cards()
        return stable_hash(
            *[
                normalize_space(card.get("text") or "")
                for card in cards
            ]
        )

    def _click_next_alert_page(self):
        page = self._page()
        before = self._article_fingerprint()

        clicked = page.locator("body").evaluate(
            r"""root => {
                const vw = window.innerWidth || 1500;
                const candidates = [...root.querySelectorAll('button,a,[role="button"]')];
                const rows = [];
                for (const el of candidates) {
                    const txt = (
                        (el.innerText || '') + ' ' +
                        (el.getAttribute('aria-label') || '') + ' ' +
                        (el.getAttribute('title') || '')
                    ).trim();

                    if (!/(suivant|suivante|next|^[>›»]$)/i.test(txt)) continue;

                    const r = el.getBoundingClientRect();
                    if (!r.width || !r.height) continue;
                    const center = r.left + r.width/2;
                    if (center < vw*0.55) continue;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                    rows.push({el, y:r.top});
                }
                rows.sort((a,b)=>b.y-a.y);
                if (!rows.length) return false;
                rows[0].el.scrollIntoView({block:'center'});
                rows[0].el.click();
                return true;
            }"""
        )

        if not clicked:
            return False

        deadline = time.time() + 7
        while time.time() < deadline:
            page.wait_for_timeout(350)
            now = self._article_fingerprint()
            if now and now != before:
                return True
        return False

    def _activate_notification(self, notif, retries=2):
        """Load /page-notifications fresh and select one exact notification.

        Each notification starts from a fresh dashboard render. This prevents a
        previous selection from poisoning the next one (the VILAVI/GEEK issue).
        Then we try the exact card and several ancestors until the right panel
        actually changes.
        """
        page = self.browser.goto(DEFAULT_NOTIFICATIONS_URL)

        try:
            page.wait_for_function(
                r"""() => {
                    const text = document.body?.innerText || '';
                    return /\d+\s+r[ée]sultat\(s\)\s+trouv[ée]\(s\)\s+pour/i.test(text);
                }""",
                timeout=12000,
            )
        except Exception:
            pass

        before = self._right_state_fingerprint()

        tagged = self._tag_notification_target(notif)
        if tagged == 0:
            return False, self._right_panel_snapshot()

        for depth in range(tagged):
            print(
                f"  -> clic cible notification profondeur {depth}"
            )

            try:
                self._click_notification_candidate(
                    notif,
                    depth,
                )
            except Exception:
                continue

            changed, panel = self._wait_panel_change(
                before,
                timeout=5,
            )

            if changed:
                return True, panel

            # Restore tags because React may have re-rendered after the click.
            tagged = self._tag_notification_target(notif)
            if tagged == 0:
                break

        # Final retry after one fresh reload.
        if retries > 1:
            print("  -> nouvelle tentative après rechargement")
            self.browser.goto(DEFAULT_NOTIFICATIONS_URL)
            tagged = self._tag_notification_target(notif)

            for depth in range(tagged):
                before = self._right_state_fingerprint()

                try:
                    self._click_notification_candidate(
                        notif,
                        depth,
                    )
                except Exception:
                    continue

                changed, panel = self._wait_panel_change(
                    before,
                    timeout=5,
                )
                if changed:
                    return True, panel

                tagged = self._tag_notification_target(notif)

        return False, self._right_panel_snapshot()

    def _detail_page_from_see_more(self, alert):
        """Click one alert's Voir plus and return the resulting detail page.

        Supports same-tab Next.js navigation and a newly opened tab/window.
        """
        page = self._page()

        # Always reconstruct the notification/card state immediately before
        # clicking a detail.
        self.browser.goto(DEFAULT_NOTIFICATIONS_URL)

        candidates = self._notification_candidates()
        if alert.notification_index >= len(candidates):
            raise RuntimeError(
                "Notification introuvable lors de l'ouverture du détail."
            )

        dummy_notif = NotificationItem(
            notification_key=alert.notification_key,
            company_or_query="",
            notification_date="",
            announced_result_count=None,
            notification_page=1,
            raw_text="",
            notification_index=alert.notification_index,
        )

        changed, _ = self._activate_notification(dummy_notif)
        if not changed:
            raise RuntimeError(
                "Impossible de recharger le panneau de la notification "
                "avant Voir plus."
            )

        # Return to the correct alert page when pagination is used.
        for _ in range(1, max(1, alert.alert_page)):
            if not self._click_next_alert_page():
                break

        cards = self._alert_cards()
        if alert.card_index >= len(cards):
            raise RuntimeError(
                f"Carte d'alerte {alert.card_index} introuvable "
                f"(cartes visibles: {len(cards)})."
            )

        # Tags were created by _alert_cards().
        button = page.locator(
            f'[data-lt-see-more="{alert.card_index}"]'
        ).first
        if button.count() == 0:
            raise RuntimeError("Bouton Voir plus introuvable.")

        existing_pages = list(self.browser.context.pages)
        old_url = str(page.url)

        button.scroll_into_view_if_needed()
        button.click(timeout=7000)

        deadline = time.time() + 10
        target_page = page

        while time.time() < deadline:
            # New tab/window case.
            for candidate in self.browser.context.pages:
                if candidate not in existing_pages:
                    target_page = candidate
                    break

            current_url = str(target_page.url or "")
            if (
                "/article/" in current_url
                or (
                    target_page is page
                    and current_url != old_url
                )
            ):
                break

            target_page.wait_for_timeout(300)

        try:
            target_page.wait_for_load_state(
                "domcontentloaded",
                timeout=5000,
            )
        except Exception:
            pass

        target_page.wait_for_timeout(1000)
        return target_page

    def _extract_detail_from_page(self, target_page, alert):
        title = ""
        for selector in ("h1", "h2", "main h3"):
            try:
                loc = target_page.locator(selector).first
                if loc.is_visible():
                    value = normalize_space(
                        loc.inner_text(timeout=1500)
                    )
                    if value:
                        title = value
                        break
            except Exception:
                pass

        if not title:
            title = normalize_space(target_page.title())

        text = self.browser._best_visible_text(target_page)
        route_url = str(target_page.url or "")

        source = alert.source
        article_id = alert.article_id
        doc_id = alert.doc_id

        if "/article/" in route_url:
            try:
                parsed = parse_article_url(
                    route_url,
                    self.browser.base_url,
                )
                source = parsed.source
                article_id = parsed.article_id
                doc_id = parsed.doc_id
                route_url = parsed.article_url
            except ValueError:
                pass

        fields = {}
        if source.casefold() == "rne":
            from modules.legaltech_browser_collector import (
                parse_rne_visible_fields,
            )
            fields = parse_rne_visible_fields(text)

        return {
            "title": title,
            "text": text,
            "fields": fields,
            "source": source,
            "article_id": article_id,
            "doc_id": doc_id,
            "article_url": route_url,
        }

    def _save_panel_debug(self, company: str):
        """Save a local diagnostic when a panel loaded but no cards were found."""
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", company).strip("_") or "notification"
        debug_dir = Path("data/legaltech_debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        page = self._page()
        try:
            (debug_dir / f"{safe}_panel.txt").write_text(
                self._right_panel_snapshot(),
                encoding="utf-8",
            )
        except Exception:
            pass

        try:
            page.screenshot(
                path=str(debug_dir / f"{safe}_panel.png"),
                full_page=False,
            )
        except Exception:
            pass

    def collect_first_notifications(
        self,
        *,
        max_notifications=3,
        max_alert_pages=3,
        safe_read_state=False,
    ):
        page = self.browser.goto(DEFAULT_NOTIFICATIONS_URL)
        if not self.browser.is_authenticated():
            raise AuthenticationRequired("Connexion LegalTech requise.")

        if safe_read_state:
            self.install_read_state_guard()

        candidates = self._notification_candidates()
        items = [
            self._parse_notification(
                row["text"],
                1,
                notification_index=index,
            )
            for index, row in enumerate(
                candidates[:max_notifications]
            )
        ]

        run_id = self.registry.start_run()
        all_alerts = []
        loaded = 0
        failed = 0

        try:
            for idx, notif in enumerate(items):
                print(
                    f"[Notification {idx+1}/{len(items)}] "
                    f"{notif.company_or_query} · {notif.notification_date or 'date ?'}"
                )
                self.registry.upsert_notification(run_id, notif)

                changed, current = self._activate_notification(
                    notif,
                    retries=2,
                )

                if not changed:
                    failed += 1
                    self.registry.update_notification_load(
                        notif.notification_key,
                        status="PANEL_NOT_UPDATED",
                        error=(
                            "Le panneau d'alertes n'a pas changé après le clic. "
                            "Les anciennes alertes ne sont pas associées à cette notification."
                        ),
                        panel_total=self._panel_total(),
                    )
                    print("  -> panneau non mis à jour; aucune donnée périmée enregistrée")
                    continue

                panel_total = self._panel_total()
                loaded += 1
                self.registry.update_notification_load(
                    notif.notification_key,
                    status="LOADED",
                    panel_total=panel_total,
                )

                notif_alerts = {}
                for ap in range(1, max_alert_pages + 1):
                    current_alerts = self._current_alerts(notif, ap)
                    print(
                        f"  -> page alertes {ap}: "
                        f"{len(current_alerts)} carte(s)"
                    )

                    if ap == 1 and not current_alerts:
                        self._save_panel_debug(notif.company_or_query)
                        print(
                            "  -> aucun article détecté; diagnostic enregistré "
                            f"dans data/legaltech_debug pour {notif.company_or_query}"
                        )

                    for alert in current_alerts:
                        notif_alerts[alert.alert_key] = alert
                        self.registry.upsert_alert(run_id, alert)

                    if panel_total is not None and len(notif_alerts) >= panel_total:
                        break
                    if not current_alerts:
                        break
                    if not self._click_next_alert_page():
                        break

                all_alerts.extend(notif_alerts.values())

            self.registry.finish_run(
                run_id,
                "COLLECTED",
                f"{loaded} notification(s) chargée(s), {failed} échec(s)",
            )
            return run_id, items, all_alerts, loaded, failed

        except Exception as exc:
            self.registry.finish_run(run_id, "FAILED", str(exc))
            raise

    def enrich(self, alerts, *, download_documents=False):
        ok = failed = downloads_ok = downloads_failed = 0

        for i, alert in enumerate(alerts, 1):
            print(
                f"[Détail {i}/{len(alerts)}] "
                f"{alert.source_label or alert.source} · "
                f"{alert.card_title or alert.article_id}"
            )

            target_page = None
            opened_new_page = False

            try:
                # Fast path when a real /article/ URL exists.
                if alert.article_url and "/article/" in alert.article_url:
                    parsed = parse_article_url(
                        alert.article_url,
                        self.browser.base_url,
                    )
                    result = BrowserResult(
                        result_key=parsed.result_key,
                        alert_url=DEFAULT_NOTIFICATIONS_URL,
                        source=parsed.source,
                        article_id=parsed.article_id,
                        doc_id=parsed.doc_id,
                        article_url=parsed.article_url,
                        list_page=alert.alert_page,
                        list_text=alert.card_text,
                    )
                    detail = self.browser.collect_detail(result)

                    self.registry.update_alert_route(
                        alert.alert_key,
                        source=parsed.source,
                        article_id=parsed.article_id,
                        doc_id=parsed.doc_id,
                        article_url=parsed.article_url,
                    )
                    self.registry.save_detail(
                        alert.alert_key,
                        detail.title,
                        detail.visible_text,
                        detail.source_fields,
                    )
                    ok += 1

                    if download_documents:
                        status, path = (
                            self.browser.try_download_visible_document(
                                result
                            )
                        )
                        self.registry.mark_download(
                            alert.alert_key,
                            status,
                            path,
                        )
                        if status == "COLLECTED":
                            downloads_ok += 1
                        else:
                            downloads_failed += 1

                    continue

                # Fallback: LegalTech exposes only a Voir plus button.
                base_page = self._page()
                before_pages = list(self.browser.context.pages)

                target_page = self._detail_page_from_see_more(alert)
                opened_new_page = target_page not in before_pages

                extracted = self._extract_detail_from_page(
                    target_page,
                    alert,
                )

                self.registry.update_alert_route(
                    alert.alert_key,
                    source=extracted["source"],
                    article_id=extracted["article_id"],
                    doc_id=extracted["doc_id"],
                    article_url=extracted["article_url"],
                )
                self.registry.save_detail(
                    alert.alert_key,
                    extracted["title"],
                    extracted["text"],
                    extracted["fields"],
                )
                ok += 1

                # PDF will be enabled only after detail extraction is stable.
                if download_documents:
                    downloads_failed += 1
                    self.registry.mark_download(
                        alert.alert_key,
                        "DEFERRED_CARD_FLOW",
                    )

            except AuthenticationRequired:
                raise
            except Exception as exc:
                self.registry.mark_detail_failed(
                    alert.alert_key,
                    str(exc),
                )
                print("  -> DETAIL FAILED:", exc)
                failed += 1
            finally:
                if target_page is not None and opened_new_page:
                    try:
                        target_page.close()
                    except Exception:
                        pass

        return ok, failed, downloads_ok, downloads_failed

    def sync(
        self,
        *,
        max_notifications=3,
        max_alert_pages=3,
        download_documents=False,
        safe_read_state=False,
    ):
        run_id, notifications, alerts, loaded, failed_notifications = (
            self.collect_first_notifications(
                max_notifications=max_notifications,
                max_alert_pages=max_alert_pages,
                safe_read_state=safe_read_state,
            )
        )
        ok, failed, downloads_ok, downloads_failed = self.enrich(
            alerts,
            download_documents=download_documents,
        )
        return SyncSummary(
            run_id=run_id,
            notifications_found=len(notifications),
            notifications_loaded=loaded,
            notifications_failed=failed_notifications,
            alerts_found=len(alerts),
            details_ok=ok,
            details_failed=failed,
            downloads_ok=downloads_ok,
            downloads_failed=downloads_failed,
        )

def summary_to_dict(x):
    return asdict(x)
