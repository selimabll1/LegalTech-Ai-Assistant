from __future__ import annotations

from pathlib import Path
import html
import json
import os
import sqlite3
import subprocess
import sys
from typing import Any

import streamlit as st


NOTIFICATIONS_DASHBOARD_VERSION = "notifications_ui_v3_modal_search_sync"
DEFAULT_DB = Path("data/legaltech_notifications_v5.sqlite3")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _safe_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _latest_run(con: sqlite3.Connection) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT * FROM runs ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _notifications(
    con: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    rows = con.execute(
        """SELECT *
           FROM notifications
           WHERE run_id=?
           ORDER BY notification_page, rowid""",
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _alerts_for_notification(
    con: sqlite3.Connection,
    run_id: str,
    notification_key: str,
) -> list[dict[str, Any]]:
    rows = con.execute(
        """SELECT *
           FROM notification_alerts
           WHERE run_id=? AND notification_key=?
           ORDER BY alert_page, rowid""",
        (run_id, notification_key),
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_fields"] = _safe_json(
            item.get("source_fields_json")
        )
        result.append(item)
    return result


def _all_alerts(
    con: sqlite3.Connection,
    run_id: str,
) -> list[dict[str, Any]]:
    rows = con.execute(
        """SELECT a.*, n.company_or_query, n.notification_date
           FROM notification_alerts a
           JOIN notifications n
             ON n.notification_key = a.notification_key
           WHERE a.run_id=?
           ORDER BY n.notification_page, a.alert_page, a.rowid""",
        (run_id,),
    ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_fields"] = _safe_json(
            item.get("source_fields_json")
        )
        result.append(item)
    return result


def _notification_identity(
    item: dict[str, Any],
) -> tuple[str, str]:
    return (
        str(item.get("company_or_query") or "").strip().casefold(),
        str(item.get("notification_date") or "").strip(),
    )


def _latest_notification_identities(
    db_path: Path,
) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
    if not db_path.exists():
        return [], set()

    con = _connect(db_path)
    try:
        run = _latest_run(con)
        if not run:
            return [], set()
        notifications = _notifications(con, run["run_id"])
        return (
            notifications,
            {_notification_identity(n) for n in notifications},
        )
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _source_label(alert: dict[str, Any]) -> str:
    return str(
        alert.get("source_label")
        or alert.get("source")
        or "Source inconnue"
    )


def _title(alert: dict[str, Any]) -> str:
    return str(
        alert.get("card_title")
        or alert.get("detail_title")
        or alert.get("article_id")
        or "Alerte LegalTech"
    )


def _pdf_path(alert: dict[str, Any]) -> Path | None:
    raw = str(alert.get("download_path") or "").strip()
    if not raw:
        return None

    path = Path(raw)
    if (
        alert.get("download_status") == "COLLECTED"
        and path.exists()
    ):
        return path
    return None


def _detail_available(alert: dict[str, Any]) -> bool:
    return bool(
        alert.get("detail_status") == "COLLECTED"
        and str(alert.get("detail_text") or "").strip()
    )


def _document_type(alert: dict[str, Any]) -> str:
    source = str(alert.get("source") or "").casefold()
    label = _source_label(alert).casefold()

    if source == "rne" or "registre national" in label:
        return "RNE"
    if source == "jort" or "journal officiel" in label:
        return "JORT"
    if source.startswith("jr") or label.startswith("journal"):
        return "Journal / Presse"
    return "Autre source LegalTech"


def _search_blob(
    notification: dict[str, Any],
    alerts: list[dict[str, Any]],
) -> str:
    chunks = [
        notification.get("company_or_query"),
        notification.get("notification_date"),
    ]

    for alert in alerts:
        chunks.extend(
            [
                _source_label(alert),
                _title(alert),
                alert.get("card_date"),
                alert.get("card_summary"),
                alert.get("detail_text"),
                alert.get("article_id"),
                alert.get("doc_id"),
                json.dumps(
                    alert.get("source_fields") or {},
                    ensure_ascii=False,
                ),
            ]
        )

    return " ".join(
        str(chunk or "")
        for chunk in chunks
    ).casefold()


def _business_fields(
    fields: dict[str, Any],
) -> list[tuple[str, str]]:
    order = [
        ("denomination", "Dénomination"),
        ("identifiant_unique", "Identifiant unique"),
        ("type_publication", "Type de publication"),
        ("type_modification", "Type de modification"),
        ("categorie_registre", "Type de registre"),
        ("capital", "Capital"),
        ("responsable", "Responsable"),
        ("qualite_responsable", "Qualité"),
        ("numero_publication", "N° publication"),
        ("bulletin_numero", "Bulletin"),
        ("date_publication", "Date de publication"),
        ("type_demande_reservation", "Demande de réservation"),
        ("numero_certificat", "N° certificat"),
        ("date_reservation", "Date de réservation"),
        ("delai_reservation", "Fin de réservation"),
        ("type_reservation", "Type de réservation"),
        ("adresse", "Adresse"),
        ("activite", "Activité"),
    ]

    result: list[tuple[str, str]] = []
    seen = set()

    for key, label in order:
        value = fields.get(key)
        if value not in (None, ""):
            result.append((label, str(value)))
            seen.add(key)

    for key, value in fields.items():
        if key in seen or value in (None, ""):
            continue
        label = key.replace("_", " ").strip().capitalize()
        result.append((label, str(value)))

    return result


def _inject_css() -> None:
    st.markdown(
        """
<style>
.lt-v3-head {
  border: 1px solid rgba(20,63,91,.12);
  border-radius: 20px;
  padding: 1.1rem 1.2rem;
  background: rgba(255,255,255,.78);
  box-shadow: 0 12px 30px rgba(20,63,91,.055);
  margin-bottom: .65rem;
}
.lt-v3-kicker {
  color: #247aa6;
  font-size: .72rem;
  font-weight: 850;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.lt-v3-title {
  color: #0b2d47;
  font-size: 1.42rem;
  font-weight: 900;
  margin-top: .12rem;
}
.lt-v3-sub {
  color: #667f90;
  font-size: .88rem;
  margin-top: .25rem;
}
.lt-v3-stat {
  border: 1px solid rgba(20,63,91,.11);
  border-radius: 15px;
  background: rgba(255,255,255,.82);
  padding: .78rem .9rem;
  height: 100%;
}
.lt-v3-stat-label {
  color: #718798;
  font-size: .67rem;
  font-weight: 850;
  letter-spacing: .055em;
  text-transform: uppercase;
}
.lt-v3-stat-value {
  color: #0b2d47;
  font-size: 1.45rem;
  font-weight: 900;
  margin-top: .18rem;
}
.lt-v3-section {
  color: #0b2d47;
  font-weight: 900;
  font-size: 1.02rem;
  margin: .9rem 0 .35rem;
}
.lt-v3-alert-meta {
  color: #728797;
  font-size: .77rem;
}
.lt-v3-type {
  display: inline-block;
  border: 1px solid #cde5f0;
  background: #eef8fc;
  color: #126b94;
  border-radius: 999px;
  padding: .18rem .5rem;
  font-size: .7rem;
  font-weight: 800;
}
.lt-v3-ok {
  display: inline-block;
  border-radius: 999px;
  padding: .16rem .46rem;
  background: #eaf7f2;
  color: #19654e;
  border: 1px solid #cde9dd;
  font-size: .69rem;
  font-weight: 800;
}
.lt-v3-missing {
  display: inline-block;
  border-radius: 999px;
  padding: .16rem .46rem;
  background: #f4f6f8;
  color: #71808c;
  border: 1px solid #e0e6ea;
  font-size: .69rem;
  font-weight: 800;
}
.lt-v3-summary {
  border-left: 3px solid #36a4d2;
  border-radius: 0 12px 12px 0;
  background: #f7fbfd;
  padding: .78rem .9rem;
  color: #17384f;
}
.lt-v3-field {
  border: 1px solid rgba(20,63,91,.1);
  border-radius: 12px;
  background: #fff;
  padding: .58rem .7rem;
  margin-bottom: .42rem;
}
.lt-v3-field-name {
  color: #798b99;
  font-size: .63rem;
  font-weight: 850;
  letter-spacing: .05em;
  text-transform: uppercase;
}
.lt-v3-field-value {
  color: #16364d;
  font-size: .86rem;
  font-weight: 650;
  margin-top: .12rem;
  overflow-wrap: anywhere;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _stat(label: str, value: Any) -> None:
    st.markdown(
        f"""
<div class="lt-v3-stat">
  <div class="lt-v3-stat-label">{html.escape(str(label))}</div>
  <div class="lt-v3-stat-value">{html.escape(str(value))}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def _field(label: str, value: str) -> None:
    st.markdown(
        f"""
<div class="lt-v3-field">
  <div class="lt-v3-field-name">{html.escape(label)}</div>
  <div class="lt-v3-field-value">{html.escape(value)}</div>
</div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Existing validated headless commands
# ---------------------------------------------------------------------------

def _run_command(
    args: list[str],
    timeout_seconds: int,
) -> tuple[bool, str]:
    project_root = Path(__file__).resolve().parents[1]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    try:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        log = (
            (exc.stdout or "")
            + "\n"
            + (exc.stderr or "")
        ).strip()
        return False, "Délai dépassé.\n\n" + log
    except Exception as exc:
        return False, f"Impossible de lancer la tâche : {exc}"

    log = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    )

    return completed.returncode == 0, log


def _sync_notifications_headless(
    max_notifications: int,
) -> tuple[bool, str]:
    return _run_command(
        [
            "-m",
            "scripts.sync_legaltech_notifications_v5",
            "--max-notifications",
            str(max_notifications),
            "--headless",
        ],
        timeout_seconds=1200,
    )


def _sync_missing_pdfs_headless() -> tuple[bool, str]:
    # This is the same PDF capture v3 that was already validated manually.
    # Explicit empty notification filter = all notifications in latest run.
    return _run_command(
        [
            "-m",
            "scripts.download_pdfs_v5_network_capture_v3",
            "--notification",
            "",
            "--limit",
            "0",
            "--headless",
        ],
        timeout_seconds=2400,
    )


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

def _render_alert_dialog_body(
    alert: dict[str, Any],
    notification: dict[str, Any],
    run: dict[str, Any],
) -> None:
    pdf = _pdf_path(alert)
    fields = alert.get("source_fields") or {}
    doc_type = _document_type(alert)

    st.markdown(f"### {_title(alert)}")

    a, b, c = st.columns([1.3, 1.25, 1.0])
    with a:
        st.caption("Notification")
        st.write(notification.get("company_or_query") or "—")
    with b:
        st.caption("Source")
        st.write(_source_label(alert))
    with c:
        st.caption("Type")
        st.markdown(
            f'<span class="lt-v3-type">{html.escape(doc_type)}</span>',
            unsafe_allow_html=True,
        )

    st.caption(
        f"Date : {alert.get('card_date') or '—'}"
    )

    summary = str(alert.get("card_summary") or "").strip()
    if summary:
        st.markdown("#### Résumé")
        st.markdown(
            f'<div class="lt-v3-summary">{html.escape(summary)}</div>',
            unsafe_allow_html=True,
        )

    business = _business_fields(fields)
    if business:
        st.markdown("#### Données clés")
        left, right = st.columns(2)
        for index, (label, value) in enumerate(business):
            with left if index % 2 == 0 else right:
                _field(label, value)

    detail = str(alert.get("detail_text") or "").strip()
    if detail:
        with st.expander("Détail complet", expanded=False):
            st.write(detail)

    st.markdown("#### PDF")
    if pdf is not None:
        st.caption(
            f"{doc_type} · {pdf.name}"
        )
        if hasattr(st, "pdf"):
            try:
                st.pdf(pdf, height=650)
            except Exception as exc:
                st.warning(
                    "Le fichier PDF existe mais le visualiseur "
                    f"n'a pas pu l'ouvrir : {exc}"
                )
        st.download_button(
            "Télécharger le PDF",
            data=pdf.read_bytes(),
            file_name=pdf.name,
            mime="application/pdf",
            width="stretch",
            key="lt_v3_modal_download_" + str(alert["alert_key"]),
        )
    else:
        st.info(
            "Aucun PDF local pour cette alerte. "
            "Utilisez « Récupérer les PDF manquants »."
        )

    with st.expander("Traçabilité technique", expanded=False):
        st.json(
            {
                "article_id": alert.get("article_id"),
                "doc_id": alert.get("doc_id"),
                "article_url": alert.get("article_url"),
                "detail_status": alert.get("detail_status"),
                "download_status": alert.get("download_status"),
                "download_path": alert.get("download_path"),
                "run_id": run.get("run_id"),
            }
        )


if hasattr(st, "dialog"):
    @st.dialog("Alerte LegalTech", width="large")
    def _alert_dialog(
        alert: dict[str, Any],
        notification: dict[str, Any],
        run: dict[str, Any],
    ) -> None:
        _render_alert_dialog_body(alert, notification, run)
else:
    def _alert_dialog(
        alert: dict[str, Any],
        notification: dict[str, Any],
        run: dict[str, Any],
    ) -> None:
        st.warning(
            "Cette version de Streamlit ne supporte pas encore "
            "les fenêtres modales. La fiche est affichée ci-dessous."
        )
        _render_alert_dialog_body(alert, notification, run)


# ---------------------------------------------------------------------------
# Main section
# ---------------------------------------------------------------------------

def render_notifications_section(
    db_path: str | Path = DEFAULT_DB,
) -> None:
    _inject_css()
    db = Path(db_path)

    st.markdown('<div id="notifications"></div>', unsafe_allow_html=True)
    st.markdown(
        """
<div class="lt-v3-head">
  <div class="lt-v3-kicker">Veille LegalTech</div>
  <div class="lt-v3-title">Notifications & alertes</div>
  <div class="lt-v3-sub">
    Synchronisez LegalTech en arrière-plan, recherchez une alerte,
    consultez ses détails et ouvrez son PDF sans quitter le dashboard.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if not db.exists():
        st.info("Aucune base locale de notifications disponible.")
        return

    con = _connect(db)
    try:
        run = _latest_run(con)
        if not run:
            st.info("Aucune synchronisation disponible.")
            return

        notifications = _notifications(con, run["run_id"])
        if not notifications:
            st.info("Aucune notification dans la dernière synchronisation.")
            return

        alerts_cache = {
            n["notification_key"]: _alerts_for_notification(
                con,
                run["run_id"],
                n["notification_key"],
            )
            for n in notifications
        }

        # -------------------- Controls --------------------
        scope_col, sync_col, pdf_col, refresh_col = st.columns(
            [1.05, 1.75, 1.75, .9]
        )

        with scope_col:
            sync_scope = st.selectbox(
                "Scanner",
                [3, 6, 10],
                index=1,
                format_func=lambda n: f"{n} notifications",
                key="lt_v3_sync_scope",
                help=(
                    "Pour le test PUNICA / PDG HISTORIAR / "
                    "DIGIARTWORK, utilisez 6 notifications. "
                    "Si leur position change, utilisez 10."
                ),
            )

        with sync_col:
            sync_clicked = st.button(
                "Récupérer / actualiser les alertes",
                width="stretch",
                key="lt_v3_sync",
            )

        with pdf_col:
            pdf_clicked = st.button(
                "Récupérer les PDF manquants",
                width="stretch",
                key="lt_v3_pdfs",
            )

        with refresh_col:
            if st.button(
                "Rafraîchir",
                width="stretch",
                key="lt_v3_refresh",
            ):
                st.rerun()

        if sync_clicked:
            before_ids = {
                _notification_identity(n)
                for n in notifications
            }

            with st.spinner(
                f"Synchronisation headless des {sync_scope} "
                "premières notifications…"
            ):
                ok, log = _sync_notifications_headless(sync_scope)

            st.session_state["lt_v3_sync_log"] = log
            st.session_state["lt_v3_sync_ok"] = ok

            if ok:
                after_notifications, after_ids = (
                    _latest_notification_identities(db)
                )
                new_ids = after_ids - before_ids
                new_items = [
                    n
                    for n in after_notifications
                    if _notification_identity(n) in new_ids
                ]

                st.session_state["lt_v3_new_items"] = [
                    (
                        n.get("company_or_query") or "—",
                        n.get("notification_date") or "—",
                    )
                    for n in new_items
                ]
                st.session_state["lt_v3_sync_message"] = (
                    "Synchronisation terminée."
                )
                st.rerun()
            else:
                st.error("La synchronisation des alertes a échoué.")
                with st.expander("Journal de synchronisation", expanded=True):
                    st.code(log or "Aucun journal.", language="text")

        if pdf_clicked:
            with st.spinner(
                "Récupération headless des PDF du dernier run…"
            ):
                ok, log = _sync_missing_pdfs_headless()

            st.session_state["lt_v3_pdf_log"] = log
            st.session_state["lt_v3_pdf_ok"] = ok

            if ok:
                st.session_state["lt_v3_pdf_message"] = (
                    "Récupération PDF terminée."
                )
                st.rerun()
            else:
                st.error("La récupération des PDF a échoué.")
                with st.expander("Journal PDF", expanded=True):
                    st.code(log or "Aucun journal.", language="text")

        if st.session_state.get("lt_v3_sync_message"):
            new_items = st.session_state.get(
                "lt_v3_new_items",
                [],
            )
            if new_items:
                pretty = " · ".join(
                    f"{company} ({date})"
                    for company, date in new_items
                )
                st.success(
                    f"{len(new_items)} nouvelle(s) notification(s) "
                    f"détectée(s) : {pretty}"
                )
            else:
                st.success(
                    "Synchronisation terminée. "
                    "Aucune nouvelle notification par rapport "
                    "au run affiché précédemment."
                )

            with st.expander(
                "Journal de la synchronisation",
                expanded=False,
            ):
                st.code(
                    st.session_state.get("lt_v3_sync_log", ""),
                    language="text",
                )

        if st.session_state.get("lt_v3_pdf_message"):
            st.success(st.session_state["lt_v3_pdf_message"])
            with st.expander("Journal PDF", expanded=False):
                st.code(
                    st.session_state.get("lt_v3_pdf_log", ""),
                    language="text",
                )

        st.caption(
            f"Dernière synchronisation : "
            f"{run.get('started_at') or '—'} · "
            "collecte exécutée en arrière-plan."
        )

        # -------------------- Search --------------------
        query = st.text_input(
            "Rechercher",
            placeholder=(
                "Entreprise, source, titre, identifiant, résumé, "
                "type de publication…"
            ),
            key="lt_v3_search",
        ).strip().casefold()

        visible_notifications = notifications

        if query:
            visible_notifications = []
            for n in notifications:
                n_alerts = alerts_cache.get(
                    n["notification_key"],
                    [],
                )
                if query in _search_blob(n, n_alerts):
                    visible_notifications.append(n)

            if not visible_notifications:
                st.info(
                    "Aucun résultat pour cette recherche "
                    "dans la dernière synchronisation."
                )
                return

        selected_key = st.selectbox(
            "Notification",
            [
                n["notification_key"]
                for n in visible_notifications
            ],
            format_func=lambda key: next(
                (
                    f"{n.get('company_or_query') or '—'} · "
                    f"{n.get('notification_date') or '—'}"
                    for n in visible_notifications
                    if n["notification_key"] == key
                ),
                key,
            ),
            key="lt_v3_notification",
        )

        notification = next(
            n
            for n in visible_notifications
            if n["notification_key"] == selected_key
        )

        alerts = alerts_cache.get(selected_key, [])

        if query:
            alerts = [
                alert
                for alert in alerts
                if query in _search_blob(
                    notification,
                    [alert],
                )
            ]

        pdf_count = sum(_pdf_path(a) is not None for a in alerts)
        detail_count = sum(_detail_available(a) for a in alerts)

        # -------------------- Stats --------------------
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            _stat(
                "Notification",
                notification.get("company_or_query") or "—",
            )
        with s2:
            _stat("Alertes", len(alerts))
        with s3:
            _stat("Détails", detail_count)
        with s4:
            _stat("PDF", pdf_count)

        # -------------------- Alert cards --------------------
        st.markdown(
            '<div class="lt-v3-section">Alertes disponibles</div>',
            unsafe_allow_html=True,
        )

        if not alerts:
            st.info("Aucune alerte correspondant au filtre.")
            return

        for index, alert in enumerate(alerts):
            pdf = _pdf_path(alert)
            doc_type = _document_type(alert)

            with st.container(border=True):
                c1, c2, c3, c4 = st.columns(
                    [1.3, 3.5, 1.0, .95]
                )

                with c1:
                    st.markdown(
                        f'<span class="lt-v3-type">'
                        f'{html.escape(doc_type)}</span>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="lt-v3-alert-meta">'
                        f'{html.escape(_source_label(alert))}</div>',
                        unsafe_allow_html=True,
                    )

                with c2:
                    st.markdown(f"**{_title(alert)}**")
                    summary = str(
                        alert.get("card_summary") or ""
                    ).strip()
                    if summary:
                        preview = (
                            summary[:170] + "…"
                            if len(summary) > 170
                            else summary
                        )
                        st.caption(preview)

                with c3:
                    st.caption(alert.get("card_date") or "—")
                    if pdf is not None:
                        st.markdown(
                            '<span class="lt-v3-ok">PDF disponible</span>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<span class="lt-v3-missing">PDF manquant</span>',
                            unsafe_allow_html=True,
                        )

                with c4:
                    if st.button(
                        "Voir",
                        width="stretch",
                        key=(
                            "lt_v3_open_"
                            + str(alert["alert_key"])
                            + "_"
                            + str(index)
                        ),
                    ):
                        _alert_dialog(
                            alert,
                            notification,
                            run,
                        )

    except sqlite3.Error as exc:
        st.error(f"Lecture de la base impossible : {exc}")
    finally:
        con.close()
