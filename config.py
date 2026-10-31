from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "JARVIS"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
DB_PATH = APP_DIR / "jarvis.sqlite3"
LOG_PATH = APP_DIR / "jarvis.log"
MODEL_CHECKPOINT_PATH = APP_DIR / "jarvis_byte_bigram.json"

RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_PATH = RESOURCE_DIR / "assets" / "jarvis.ico"
DASHBOARD_HTML_PATH = RESOURCE_DIR / "dashboard.html"
LOGO_IMAGE_PATH = RESOURCE_DIR / "assets" / "icons" / "jarvis-logo.png"
REFERENCE_IMAGE_PATH = RESOURCE_DIR / "assets" / "ui_gui_images" / "reference_dashboard.png"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
