
import argparse
import json
from pathlib import Path

from modules.legaltech_browser_collector import (
    AuthenticationRequired,
    LegalTechBrowserCollector,
)
from modules.legaltech_notifications_network_collector import (
    DEFAULT_V5_DB,
    NetworkFirstNotificationsCollector,
)
from modules.legaltech_notifications_collector import (
    summary_to_dict,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-notifications",
        type=int,
        default=3,
    )
    parser.add_argument(
        "--download-pdf",
        action="store_true",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
    )
    args = parser.parse_args()

    if args.reset_db:
        for path in (
            DEFAULT_V5_DB,
            Path(str(DEFAULT_V5_DB) + "-wal"),
            Path(str(DEFAULT_V5_DB) + "-shm"),
        ):
            path.unlink(missing_ok=True)
        print("Base v5 réinitialisée.")

    try:
        with LegalTechBrowserCollector(
            headless=args.headless,
            slow_mo_ms=120 if not args.headless else 0,
        ) as browser:
            collector = NetworkFirstNotificationsCollector(
                browser
            )

            summary = collector.sync(
                max_notifications=args.max_notifications,
                max_alert_pages=1,
                download_documents=args.download_pdf,
                safe_read_state=False,
            )

            print("\nSYNC V5 NETWORK-FIRST TERMINÉE")
            print(
                json.dumps(
                    summary_to_dict(summary),
                    indent=2,
                    ensure_ascii=False,
                )
            )
            print("Base:", DEFAULT_V5_DB)

    except AuthenticationRequired as exc:
        print("AUTH_REQUIRED")
        print(exc)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
