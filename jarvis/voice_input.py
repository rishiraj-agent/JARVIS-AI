from __future__ import annotations

import threading


class VoiceInput:
    """Reserved offline speech interface; no cloud transcription is used."""

    def __init__(self, timeout: int = 8, phrase_limit: int = 15, language: str = "en-IN") -> None:
        self.timeout = timeout
        self.phrase_limit = phrase_limit
        self.language = language

    def listen(self, cancelled: threading.Event | None = None) -> str:
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError("Listening stopped.")
        raise RuntimeError(
            "Offline speech recognition is not implemented yet. Use text chat; "
            "JARVIS will not send microphone audio to an online service."
        )
