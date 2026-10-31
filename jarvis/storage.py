from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS settings "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS messages "
                "(id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, "
                "created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS notes "
                "(id INTEGER PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, "
                "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS reminders "
                "(id INTEGER PRIMARY KEY, title TEXT NOT NULL, due_at TEXT NOT NULL, "
                "details TEXT NOT NULL DEFAULT '', completed INTEGER NOT NULL DEFAULT 0, "
                "created_at TEXT NOT NULL)"
            )
            reminder_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(reminders)")
            }
            if "details" not in reminder_columns:
                connection.execute(
                    "ALTER TABLE reminders ADD COLUMN details TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_version "
                "(version INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT INTO schema_version(version) "
                "SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM schema_version)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS shortcuts "
                "(id INTEGER PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS searches "
                "(id INTEGER PRIMARY KEY, query TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS memories "
                "(id INTEGER PRIMARY KEY, key TEXT NOT NULL COLLATE NOCASE UNIQUE, "
                "value TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS knowledge_documents "
                "(id INTEGER PRIMARY KEY, source TEXT NOT NULL, checksum TEXT NOT NULL UNIQUE, "
                "added_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS knowledge_chunks "
                "(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, "
                "chunk_index INTEGER NOT NULL, content TEXT NOT NULL, "
                "FOREIGN KEY(document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS knowledge_chunks_document_idx "
                "ON knowledge_chunks(document_id, chunk_index)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS knowledge_documents_source_idx "
                "ON knowledge_documents(source)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                yield connection
        finally:
            connection.close()

    def get_settings(self) -> dict[str, object]:
        with self._connect() as connection:
            rows = connection.execute("SELECT key, value FROM settings").fetchall()
        return {key: json.loads(value) for key, value in rows}

    def save_settings(self, settings: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [(key, json.dumps(value)) for key, value in settings.items()],
            )

    def add_message(self, role: str, content: str, limit: int = 100) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO messages(role, content, created_at) VALUES(?, ?, ?)",
                (role, content, datetime.now().astimezone().isoformat(timespec="seconds")),
            )
            connection.execute(
                "DELETE FROM messages WHERE id NOT IN "
                "(SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
                (limit,),
            )

    def message_timestamps(self, limit: int = 40) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT created_at FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [created_at for (created_at,) in reversed(rows)]

    def get_messages(self, limit: int = 40) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [{"role": role, "content": content} for role, content in reversed(rows)]

    def clear_messages(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages")

    def get_memories(self, query: str = "") -> list[dict[str, object]]:
        with self._connect() as connection:
            if query.strip():
                match = f"%{query.strip()}%"
                rows = connection.execute(
                    "SELECT id, key, value, created_at, updated_at FROM memories "
                    "WHERE key LIKE ? OR value LIKE ? ORDER BY updated_at DESC",
                    (match, match),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id, key, value, created_at, updated_at FROM memories "
                    "ORDER BY updated_at DESC"
                ).fetchall()
        return [
            {"id": row[0], "key": row[1], "value": row[2],
             "created_at": row[3], "updated_at": row[4]}
            for row in rows
        ]

    def save_memory(self, key: str, value: str) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memories(key, value, created_at, updated_at) VALUES(?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, now, now),
            )
            row = connection.execute(
                "SELECT id FROM memories WHERE key = ?", (key,)
            ).fetchone()
        return int(row[0])

    def delete_memory(self, memory_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

    def add_knowledge_document(
        self, source: str, checksum: str, chunks: list[str]
    ) -> tuple[int, bool]:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM knowledge_documents WHERE checksum = ?", (checksum,)
            ).fetchone()
            if existing:
                return int(existing[0]), False
            cursor = connection.execute(
                "INSERT INTO knowledge_documents(source, checksum, added_at) VALUES(?, ?, ?)",
                (source, checksum, now),
            )
            document_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO knowledge_chunks(document_id, chunk_index, content) VALUES(?, ?, ?)",
                [(document_id, index, content) for index, content in enumerate(chunks)],
            )
        return document_id, True

    def get_knowledge_documents(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT d.id, d.source, d.added_at, COUNT(c.id) "
                "FROM knowledge_documents d LEFT JOIN knowledge_chunks c "
                "ON c.document_id = d.id GROUP BY d.id ORDER BY d.added_at DESC"
            ).fetchall()
        return [
            {"id": row[0], "source": row[1], "added_at": row[2], "chunks": row[3]}
            for row in rows
        ]

    def search_knowledge_candidates(
        self, terms: list[str], limit: int = 400
    ) -> list[dict[str, object]]:
        clean_terms = [term for term in terms if term and len(term) <= 64][:8]
        if not clean_terms:
            return []
        limit = max(1, min(int(limit), 500))
        clauses = " OR ".join("c.content LIKE ?" for _ in clean_terms)
        params = [f"%{term}%" for term in clean_terms]
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT d.source, c.content FROM knowledge_chunks c "
                "JOIN knowledge_documents d ON d.id = c.document_id "
                f"WHERE {clauses} LIMIT ?",
                params,
            ).fetchall()
        return [{"source": row[0], "content": row[1]} for row in rows]

    def delete_knowledge_document(self, document_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,))
            connection.execute("DELETE FROM knowledge_documents WHERE id = ?", (document_id,))

    def get_notes(self, query: str = "") -> list[dict[str, object]]:
        with self._connect() as connection:
            if query.strip():
                match = f"%{query.strip()}%"
                rows = connection.execute(
                    "SELECT id, title, body, created_at, updated_at FROM notes "
                    "WHERE title LIKE ? OR body LIKE ? ORDER BY updated_at DESC",
                    (match, match),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id, title, body, created_at, updated_at FROM notes "
                    "ORDER BY updated_at DESC"
                ).fetchall()
        return [
            {"id": row[0], "title": row[1], "body": row[2],
             "created_at": row[3], "updated_at": row[4]}
            for row in rows
        ]

    def save_note(self, title: str, body: str, note_id: int | None = None) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            if note_id is None:
                cursor = connection.execute(
                    "INSERT INTO notes(title, body, created_at, updated_at) VALUES(?, ?, ?, ?)",
                    (title, body, now, now),
                )
                return int(cursor.lastrowid)
            connection.execute(
                "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                (title, body, now, note_id),
            )
            return note_id

    def delete_note(self, note_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM notes WHERE id = ?", (note_id,))

    def get_reminders(self, include_completed: bool = True) -> list[dict[str, object]]:
        with self._connect() as connection:
            clause = "" if include_completed else "WHERE completed = 0"
            rows = connection.execute(
                "SELECT id, title, due_at, details, completed FROM reminders "
                f"{clause} ORDER BY completed, due_at"
            ).fetchall()
        return [
            {"id": row[0], "title": row[1], "due_at": row[2],
             "details": row[3], "completed": bool(row[4])}
            for row in rows
        ]

    def save_reminder(
        self, title: str, due_at: str, details: str = "", reminder_id: int | None = None
    ) -> int:
        with self._connect() as connection:
            if reminder_id is None:
                cursor = connection.execute(
                    "INSERT INTO reminders(title, due_at, details, created_at) "
                    "VALUES(?, ?, ?, ?)",
                    (
                        title, due_at, details,
                        datetime.now().astimezone().isoformat(timespec="seconds"),
                    ),
                )
                return int(cursor.lastrowid)
            connection.execute(
                "UPDATE reminders SET title = ?, due_at = ?, details = ? WHERE id = ?",
                (title, due_at, details, reminder_id),
            )
            return reminder_id

    def set_reminder_completed(self, reminder_id: int, completed: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE reminders SET completed = ? WHERE id = ?",
                (int(completed), reminder_id),
            )

    def delete_reminder(self, reminder_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    def get_shortcuts(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, path FROM shortcuts ORDER BY name"
            ).fetchall()
        return [{"id": row[0], "name": row[1], "path": row[2]} for row in rows]

    def save_shortcut(self, name: str, path: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO shortcuts(name, path) VALUES(?, ?) "
                "ON CONFLICT(path) DO UPDATE SET name = excluded.name",
                (name, path),
            )
            row = connection.execute(
                "SELECT id FROM shortcuts WHERE path = ?", (path,)
            ).fetchone()
        return int(row[0]) if row else int(cursor.lastrowid)

    def delete_shortcut(self, shortcut_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM shortcuts WHERE id = ?", (shortcut_id,))

    def add_search(self, query: str, limit: int = 20) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO searches(query, created_at) VALUES(?, ?)",
                (query, datetime.now().astimezone().isoformat(timespec="seconds")),
            )
            connection.execute(
                "DELETE FROM searches WHERE id NOT IN "
                "(SELECT id FROM searches ORDER BY id DESC LIMIT ?)", (limit,)
            )

    def get_searches(self, limit: int = 20) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT query FROM searches ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [query for (query,) in rows]

    def delete_all(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM messages")
            connection.execute("DELETE FROM settings")
            connection.execute("DELETE FROM notes")
            connection.execute("DELETE FROM reminders")
            connection.execute("DELETE FROM shortcuts")
            connection.execute("DELETE FROM searches")
            connection.execute("DELETE FROM memories")
            connection.execute("DELETE FROM knowledge_chunks")
            connection.execute("DELETE FROM knowledge_documents")
