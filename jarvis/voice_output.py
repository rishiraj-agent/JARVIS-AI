from __future__ import annotations

import queue
import threading
from collections.abc import Callable


class VoiceOutput:
    def __init__(self, on_done: Callable[[], None] | None = None) -> None:
        self._queue: queue.Queue[tuple[str, threading.Event] | None] = queue.Queue()
        self._stop_current = threading.Event()
        self._on_done = on_done
        self._engine = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-tts")
        self.available = False
        self.error: str | None = None
        self._thread.start()

    def speak(self, text: str) -> None:
        self._queue.put((text, self._stop_current))

    def stop(self) -> None:
        self._stop_current.set()
        self._stop_current = threading.Event()
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                self.available = False
                self.error = "Speech output could not be interrupted by the audio engine."

    def _run(self) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            self._engine = engine
            self.available = True
        except Exception as error:
            self.error = f"Speech output is unavailable: {error.__class__.__name__}."
            while True:
                item = self._queue.get()
                if item is None:
                    return
                if self._on_done is not None:
                    self._on_done()
        while True:
            item = self._queue.get()
            if item is None:
                return
            text, stop_event = item
            if stop_event.is_set():
                if self._on_done is not None:
                    self._on_done()
                continue
            try:
                engine.say(text)
                engine.runAndWait()
            except Exception:
                self.available = False
                self.error = "Speech output encountered an audio engine error."
            finally:
                if self._on_done is not None:
                    self._on_done()
