"""Registre SQLite pour éviter les téléchargements et analyses en double."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

LEGALTECH_REGISTRY_VERSION = "legaltech_registry_v1"


class LegalTechRegistry:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'legaltech',
                    source_id TEXT,
                    reference TEXT,
                    source_url TEXT,
                    download_url TEXT,
                    filename TEXT NOT NULL,
                    local_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    published_at TEXT,
                    collected_at TEXT NOT NULL,
                    processing_status TEXT NOT NULL DEFAULT 'COLLECTED',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_sha256
                    ON documents(sha256);
                CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_id
                    ON documents(source, source_id)
                    WHERE source_id IS NOT NULL AND source_id <> '';
                CREATE INDEX IF NOT EXISTS idx_documents_reference
                    ON documents(reference);
                """
            )

    def has_source_id(self, source_id: str | None) -> bool:
        if not source_id:
            return False
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM documents WHERE source='legaltech' AND source_id=? LIMIT 1",
                (source_id,),
            ).fetchone()
        return row is not None

    def register(
        self,
        *,
        source_id: str | None,
        reference: str | None,
        source_url: str | None,
        download_url: str | None,
        filename: str,
        local_path: str | Path,
        sha256: str,
        size_bytes: int,
        published_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO documents (
                        source, source_id, reference, source_url, download_url,
                        filename, local_path, sha256, size_bytes, published_at,
                        collected_at, processing_status, metadata_json
                    ) VALUES ('legaltech', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COLLECTED', ?)
                    """,
                    (
                        source_id,
                        reference,
                        source_url,
                        download_url,
                        filename,
                        str(Path(local_path)),
                        sha256,
                        int(size_bytes),
                        published_at,
                        datetime.now(timezone.utc).isoformat(),
                        json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
                    ),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM documents ORDER BY collected_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [dict(row) for row in rows]
