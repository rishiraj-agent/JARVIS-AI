from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from pathlib import Path

from jarvis.storage import Storage


class NotesService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def search(self, query: str = "") -> list[dict[str, object]]:
        return self.storage.get_notes(query)

    def save(self, title: str, body: str, note_id: int | None = None) -> int:
        normalized_title = title.strip()
        normalized_body = body.strip()
        if not normalized_title:
            raise ValueError("A note title is required.")
        if not normalized_body:
            raise ValueError("Note content cannot be empty.")
        if len(normalized_title) > 160:
            raise ValueError("Note title must be 160 characters or fewer.")
        return self.storage.save_note(normalized_title, normalized_body, note_id)

    def delete(self, note_id: int) -> None:
        self.storage.delete_note(note_id)


class ReminderService:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def create(
        self, title: str, due_at: str, details: str = "", reminder_id: int | None = None
    ) -> int:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("A reminder title is required.")
        if len(normalized_title) > 160:
            raise ValueError("Reminder title must be 160 characters or fewer.")
        normalized_details = details.strip()
        if len(normalized_details) > 2000:
            raise ValueError("Reminder details must be 2000 characters or fewer.")
        from datetime import datetime

        try:
            parsed = datetime.fromisoformat(due_at)
        except ValueError:
            raise ValueError("Enter a valid date and time.") from None
        if parsed.tzinfo is None:
            parsed = parsed.astimezone()
        return self.storage.save_reminder(
            normalized_title, parsed.isoformat(timespec="minutes"),
            normalized_details, reminder_id,
        )

    def upcoming(self) -> list[dict[str, object]]:
        return self.storage.get_reminders(include_completed=False)

    def complete(self, reminder_id: int, completed: bool = True) -> None:
        self.storage.set_reminder_completed(reminder_id, completed)

    def delete(self, reminder_id: int) -> None:
        self.storage.delete_reminder(reminder_id)


class MemoryCore:
    """Explicit, user-controlled memory stored only in the local SQLite database."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def remember(self, key: str, value: str) -> int:
        key = " ".join(key.split())
        value = " ".join(value.split())
        if not key or not value:
            raise ValueError("Memory needs both a name and a value.")
        if len(key) > 80:
            raise ValueError("Memory name must be 80 characters or fewer.")
        if len(value) > 1000:
            raise ValueError("Memory value must be 1000 characters or fewer.")
        return self.storage.save_memory(key, value)

    def recall(self, query: str = "") -> list[dict[str, object]]:
        return self.storage.get_memories(query.strip())

    def forget(self, memory_id: int) -> None:
        self.storage.delete_memory(memory_id)


class KnowledgeBase:
    """Local TXT/CSV import and explainable keyword retrieval; no embeddings or API."""

    MAX_FILE_BYTES = 2 * 1024 * 1024
    MAX_CSV_ROWS = 10_000
    CHUNK_CHARS = 900
    STOP_WORDS = {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
        "or", "that", "the", "this", "to", "was", "what", "when", "where",
        "which", "who", "why", "with", "you", "your", "hai", "hain", "ka",
        "ki", "ko", "ke", "kya", "mein", "me", "aur", "se", "ye", "woh",
    }

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    def documents(self) -> list[dict[str, object]]:
        return self.storage.get_knowledge_documents()

    def import_file(self, file_path: str | Path) -> tuple[int, int, bool]:
        path = Path(file_path)
        if path.suffix.lower() not in {".txt", ".csv"}:
            raise ValueError("Only TXT and CSV knowledge files are supported.")
        try:
            size = path.stat().st_size
        except OSError as error:
            raise ValueError(f"Cannot read the selected file: {error}") from None
        if size <= 0:
            raise ValueError("The selected file is empty.")
        if size > self.MAX_FILE_BYTES:
            raise ValueError("For low-memory safety, each imported file must be 2 MiB or smaller.")
        try:
            raw = path.read_bytes()
            if len(raw) > self.MAX_FILE_BYTES:
                raise ValueError("For low-memory safety, each imported file must be 2 MiB or smaller.")
            text = raw.decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"Could not read UTF-8 text from this file: {error}") from None

        if path.suffix.lower() == ".csv":
            lines: list[str] = []
            try:
                for index, row in enumerate(csv.reader(io.StringIO(text, newline=""))):
                    if index >= self.MAX_CSV_ROWS:
                        raise ValueError("CSV is limited to 10,000 rows per import.")
                    line = " | ".join(cell.strip() for cell in row if cell.strip())
                    if line:
                        lines.append(line)
            except csv.Error as error:
                raise ValueError(f"CSV format error: {error}") from None
            text = "\n\n".join(lines)

        chunks = self._make_chunks(text)
        if not chunks:
            raise ValueError("The file contains no usable text.")
        checksum = hashlib.sha256(raw).hexdigest()
        document_id, added = self.storage.add_knowledge_document(
            path.name[:255], checksum, chunks
        )
        return document_id, len(chunks), added

    def _make_chunks(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        pieces: list[str] = []
        for paragraph in paragraphs:
            remaining = paragraph
            while len(remaining) > self.CHUNK_CHARS:
                cut = remaining.rfind(" ", 0, self.CHUNK_CHARS + 1)
                if cut < self.CHUNK_CHARS // 2:
                    cut = self.CHUNK_CHARS
                pieces.append(remaining[:cut].strip())
                remaining = remaining[cut:].strip()
            if remaining:
                pieces.append(remaining)

        chunks: list[str] = []
        pending = ""
        for piece in pieces:
            if pending and len(pending) + len(piece) + 2 > self.CHUNK_CHARS:
                chunks.append(pending)
                pending = ""
            pending = f"{pending}\n\n{piece}" if pending else piece
        if pending:
            chunks.append(pending)
        return chunks

    def search(self, query: str, limit: int = 3) -> list[dict[str, object]]:
        terms = list(dict.fromkeys(
            token for token in re.findall(r"[^\W_]+", query.casefold(), re.UNICODE)
            if len(token) > 1 and token not in self.STOP_WORDS
        ))[:8]
        if not terms:
            return []
        candidates = self.storage.search_knowledge_candidates(terms)
        if not candidates:
            return []

        tokenized = [
            (item, re.findall(r"[^\W_]+", str(item["content"]).casefold(), re.UNICODE))
            for item in candidates
        ]
        token_sets = [set(tokens) for _, tokens in tokenized]
        document_frequency = {
            term: sum(term in token_set for token_set in token_sets)
            for term in terms
        }
        ranked: list[dict[str, object]] = []
        corpus_size = len(tokenized)
        for item, tokens in tokenized:
            counts: dict[str, int] = {}
            for token in tokens:
                if token in terms:
                    counts[token] = counts.get(token, 0) + 1
            if not counts:
                continue
            score = 0.0
            for term, frequency in counts.items():
                df = document_frequency[term]
                inverse_frequency = math.log(1.0 + (corpus_size - df + 0.5) / (df + 0.5))
                score += (1.0 + math.log(frequency)) * inverse_frequency
            ranked.append({
                "source": item["source"],
                "content": item["content"],
                "score": score,
                "matched_terms": sorted(counts),
            })
        ranked.sort(key=lambda item: float(item["score"]), reverse=True)
        return ranked[:max(1, min(int(limit), 5))]

    def forget_document(self, document_id: int) -> None:
        self.storage.delete_knowledge_document(document_id)
