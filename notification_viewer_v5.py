
from pathlib import Path
import json
import sqlite3

import pandas as pd
import streamlit as st

DB = Path("data/legaltech_notifications_v5.sqlite3")

st.set_page_config(
    page_title="LegalTech Notifications v5",
    layout="wide",
)
st.title(
    "LegalTech — Notifications, alertes & détails · v5"
)

if not DB.exists():
    st.warning(
        "Aucune base v5. Lancez d'abord "
        "`python -m scripts.sync_legaltech_notifications_v5`."
    )
    st.stop()

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

run = con.execute(
    """SELECT * FROM runs
       ORDER BY started_at DESC
       LIMIT 1"""
).fetchone()

if not run:
    st.info("Aucune collecte v5.")
    st.stop()

run = dict(run)

st.caption(
    f"Dernière collecte: {run['started_at']} · "
    f"statut {run['status']}"
)

notifications = [
    dict(row)
    for row in con.execute(
        """SELECT *
           FROM notifications
           WHERE run_id=?
           ORDER BY notification_index, rowid""",
        (run["run_id"],),
    ).fetchall()
]

if not notifications:
    st.info("Aucune notification collectée.")
    st.stop()

left, right = st.columns([0.29, 0.71])

with left:
    st.subheader("Notifications")

    selected = st.radio(
        "Notification",
        [x["notification_key"] for x in notifications],
        format_func=lambda key: next(
            (
                f"{x['company_or_query']} · "
                f"{x['notification_date'] or 'date ?'}"
                for x in notifications
                if x["notification_key"] == key
            ),
            key,
        ),
        label_visibility="collapsed",
    )

notif = next(
    x for x in notifications
    if x["notification_key"] == selected
)

alerts = [
    dict(row)
    for row in con.execute(
        """SELECT *
           FROM notification_alerts
           WHERE run_id=? AND notification_key=?
           ORDER BY card_index, rowid""",
        (run["run_id"], selected),
    ).fetchall()
]

with right:
    st.header(notif["company_or_query"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Date notification",
        notif["notification_date"] or "—",
    )
    c2.metric(
        "Résultats annoncés",
        notif["announced_result_count"]
        if notif["announced_result_count"] is not None
        else "—",
    )
    c3.metric(
        "Alertes récupérées",
        len(alerts),
    )
    c4.metric(
        "Méthode",
        notif["load_status"],
    )

    if not alerts:
        st.error(
            "Aucune alerte récupérée pour cette notification."
        )
        if notif["load_error"]:
            st.caption(notif["load_error"])
    else:
        rows = []
        for alert in alerts:
            rows.append(
                {
                    "Source": (
                        alert["source_label"]
                        or alert["source"]
                    ),
                    "Date": alert["card_date"] or "—",
                    "Titre": (
                        alert["card_title"]
                        or alert["detail_title"]
                        or "—"
                    ),
                    "Résumé": (
                        alert["card_summary"] or "—"
                    ),
                    "Détail": alert["detail_status"],
                    "PDF": alert["download_status"],
                }
            )

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

        mapping = {
            alert["alert_key"]: alert
            for alert in alerts
        }

        chosen = st.selectbox(
            "Alerte",
            list(mapping.keys()),
            format_func=lambda key: (
                f"{mapping[key]['source_label'] or mapping[key]['source']} · "
                f"{mapping[key]['card_date'] or ''} · "
                f"{mapping[key]['card_title'] or mapping[key]['article_id']}"
            ),
        )

        alert = mapping[chosen]

        st.markdown("### Informations de l'alerte")

        a, b = st.columns(2)

        with a:
            st.write(
                "**Entreprise / notification :**",
                notif["company_or_query"],
            )
            st.write(
                "**Source :**",
                alert["source_label"] or alert["source"],
            )
            st.write(
                "**Date :**",
                alert["card_date"] or "—",
            )
            st.write(
                "**Titre :**",
                alert["card_title"]
                or alert["detail_title"]
                or "—",
            )

        with b:
            st.write(
                "**Article ID :**",
                alert["article_id"] or "—",
            )
            st.write(
                "**Doc ID :**",
                alert["doc_id"] or "—",
            )
            st.write(
                "**Détail :**",
                alert["detail_status"],
            )
            st.write(
                "**PDF :**",
                alert["download_status"],
            )

        st.markdown("#### Résumé")
        st.write(alert["card_summary"] or "—")

        st.markdown("#### Détail complet")
        st.write(
            alert["detail_text"]
            or "Aucun détail supplémentaire disponible."
        )

        try:
            fields = json.loads(
                alert["source_fields_json"] or "{}"
            )
        except Exception:
            fields = {}

        if fields:
            st.markdown("#### Données structurées")
            st.json(fields)

        if alert["download_path"]:
            pdf = Path(alert["download_path"])
            if pdf.exists():
                st.markdown("#### PDF")
                try:
                    st.pdf(str(pdf), height=800)
                except Exception:
                    st.info(
                        f"PDF enregistré : {pdf}"
                    )

        with st.expander("Traçabilité"):
            st.json(alert)

con.close()
