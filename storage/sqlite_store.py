import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

from config import settings
from logging_config import get_logger
from models.paper import FavoriteRecord, SearchHistoryRecord

logger = get_logger(__name__)


class SQLiteStore:
    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or settings.sqlite_path
        self._lock = threading.Lock()
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        directory = os.path.dirname(self._db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._lock:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query TEXT NOT NULL,
                        year_from INTEGER,
                        year_to INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS favorites (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        doi_or_id TEXT NOT NULL UNIQUE,
                        paper_title TEXT,
                        note TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def add_search_history(
        self, query: str, year_from: Optional[int] = None, year_to: Optional[int] = None
    ) -> int:
        with self._lock:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO search_history (query, year_from, year_to) VALUES (?, ?, ?)",
                    (query, year_from, year_to),
                )
                return cursor.lastrowid

    def get_search_history(self, limit: int = 50) -> List[SearchHistoryRecord]:
        with self._lock:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, query, year_from, year_to, created_at FROM search_history ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = cursor.fetchall()
                return [
                    SearchHistoryRecord(
                        id=r["id"],
                        query=r["query"],
                        year_from=r["year_from"],
                        year_to=r["year_to"],
                        created_at=datetime.fromisoformat(r["created_at"]),
                    )
                    for r in rows
                ]

    def add_favorite(
        self, doi_or_id: str, paper_title: Optional[str] = None, note: Optional[str] = None
    ) -> int:
        with self._lock:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO favorites (doi_or_id, paper_title, note)
                    VALUES (?, ?, COALESCE(?, (SELECT note FROM favorites WHERE doi_or_id = ?)))
                    """,
                    (doi_or_id, paper_title, note, doi_or_id),
                )
                return cursor.lastrowid

    def get_favorites(self) -> List[FavoriteRecord]:
        with self._lock:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, doi_or_id, paper_title, note, created_at FROM favorites ORDER BY created_at DESC"
                )
                rows = cursor.fetchall()
                return [
                    FavoriteRecord(
                        id=r["id"],
                        doi_or_id=r["doi_or_id"],
                        paper_title=r["paper_title"],
                        note=r["note"],
                        created_at=datetime.fromisoformat(r["created_at"]),
                    )
                    for r in rows
                ]

    def remove_favorite(self, doi_or_id: str) -> bool:
        with self._lock:
            with self._conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM favorites WHERE doi_or_id = ?", (doi_or_id,))
                return cursor.rowcount > 0


_store: Optional[SQLiteStore] = None


def get_store() -> SQLiteStore:
    global _store
    if _store is None:
        _store = SQLiteStore()
    return _store
