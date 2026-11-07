"""Temporary runtime database (SQLite) for prediction history — PRD §16.

Only session-scoped data lives here: one row per prediction, deleted at startup,
by expiry, by explicit delete, or on graceful shutdown. No permanent storage.
"""

from app.db.history_repository import HistoryRecord, HistoryRepository

__all__ = ["HistoryRecord", "HistoryRepository"]
