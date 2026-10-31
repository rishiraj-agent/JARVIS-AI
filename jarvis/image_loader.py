from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path


class ImageLoader:
    """Load optional local PNG/GIF images without making them UI dependencies."""

    def __init__(self) -> None:
        self._images: dict[tuple[Path, int], tk.PhotoImage] = {}

    def load(self, path: Path, max_width: int = 0, max_height: int = 0) -> tk.PhotoImage | None:
        source = path.resolve()
        if not source.is_file():
            return None
        try:
            image = tk.PhotoImage(file=str(source))
            factor = max(
                1,
                (image.width() + max_width - 1) // max_width if max_width else 1,
                (image.height() + max_height - 1) // max_height if max_height else 1,
            )
            if factor > 1:
                image = image.subsample(factor, factor)
            self._images[(source, factor)] = image
            return image
        except (tk.TclError, OSError):
            logging.warning("Optional UI image could not be loaded: %s", source.name)
            return None
