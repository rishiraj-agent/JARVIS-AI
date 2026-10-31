from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable
import platform

try:
    import psutil
except ImportError:  # Optional metrics dependency.
    psutil = None
from jarvis.web_search import open_search, open_website


APP_ALLOWLIST = {
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notepad": "notepad.exe",
    "paint": "mspaint.exe",
}


def run_command(
    text: str,
    choose_directory: Callable[[], str] | None = None,
) -> str | None:
    command = text.strip()
    lowered = command.lower()
    if re.fullmatch(
        r"(?:(?:what(?:'s| is)?|tell me)\s+(?:the\s+)?)?"
        r"(?:current\s+)?time(?:\s+is it|\s+please)?[?.!]*",
        lowered,
    ):
        return datetime.now().astimezone().strftime("It is %I:%M %p on %A, %B %d, %Y.")
    if re.fullmatch(
        r"(?:(?:what(?:'s| is)?|tell me)\s+(?:the\s+)?)?"
        r"(?:today(?:'s)?\s+)?date[?.!]*",
        lowered,
    ):
        return datetime.now().astimezone().strftime("Today is %A, %B %d, %Y.")

    app_match = re.fullmatch(r"(?:open|launch|start)\s+(calculator|calc|notepad|paint)[?.!]*", lowered)
    if app_match:
        executable = APP_ALLOWLIST[app_match.group(1)]
        try:
            subprocess.Popen([executable], shell=False)
            return f"Opened {app_match.group(1).capitalize()}."
        except OSError:
            return f"Windows couldn't open {app_match.group(1)}. Check that the app is available."

    web_match = re.fullmatch(r"(?:open|go to|visit)\s+(.+)", command, re.IGNORECASE)
    if web_match:
        return open_website(web_match.group(1).strip(" .!?"))
    search_match = re.fullmatch(r"(?:search (?:the )?web for|google)\s+(.+)", command, re.IGNORECASE)
    if search_match:
        return open_search(search_match.group(1).strip(" .!?"))

    note_match = re.fullmatch(r"(?:create|save|write)\s+(?:a\s+)?note(?:\s*:\s*|\s+)(.+)", command, re.IGNORECASE | re.DOTALL)
    if note_match:
        content = note_match.group(1).strip()
        if not content:
            return "Please include the note text after 'create note'."
        notes_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "JARVIS" / "notes"
        try:
            notes_dir.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("note-%Y%m%d-%H%M%S-%f.txt")
            (notes_dir / name).write_text(content + "\n", encoding="utf-8")
            return f"Saved your note locally as {name}."
        except OSError:
            return "I couldn't save the note. Check that your user account can write to its AppData folder."

    if re.fullmatch(r"(?:search|find)\s+(?:for\s+)?files?[?.!]*", lowered):
        if choose_directory is None:
            return "Use the folder picker in JARVIS to choose where to search."
        folder = choose_directory()
        if not folder:
            return "File search cancelled."
        try:
            root = Path(folder)
            results: list[str] = []
            scan_errors: list[str] = []
            for path, directories, filenames in os.walk(
                root,
                onerror=lambda error: scan_errors.append(error.filename or "an inaccessible folder"),
            ):
                directories[:] = [name for name in directories if name not in {"$Recycle.Bin", "System Volume Information"}]
                for filename in filenames:
                    results.append(str(Path(path) / filename))
                    if len(results) >= 500:
                        break
                if len(results) >= 500:
                    break
            if not results:
                return f"No files were found in {root}."
            suffix = "\n(Showing the first 500 files.)" if len(results) == 500 else ""
            if scan_errors:
                skipped = ", ".join(scan_errors[:3])
                more = " and other folders" if len(scan_errors) > 3 else ""
                suffix += f"\nSome folders could not be read: {skipped}{more}."
            return f"Found {len(results)} files under {root}:\n" + "\n".join(results) + suffix
        except (OSError, PermissionError):
            return "I couldn't read that folder. Choose a directory your account can access."

    if re.fullmatch(r"(?:show|get|check)\s+(?:my\s+)?system\s+(?:and\s+)?network\s+status[?.!]*", lowered):
        return _system_status()

    volume_match = re.fullmatch(r"(?:set|adjust)\s+(?:the\s+)?volume\s+to\s+(\d{1,3})%?[?.!]*", lowered)
    if volume_match:
        percentage = int(volume_match.group(1))
        if not 0 <= percentage <= 100:
            return "Volume must be between 0 and 100 percent."
        if sys.platform != "win32":
            return "Windows system-volume control is not available on this platform."
        try:
            value = round(0xFFFF * percentage / 100)
            packed = value | (value << 16)
            result = ctypes.windll.winmm.waveOutSetVolume(0, packed)
            if result != 0:
                return "Windows could not adjust the master audio volume."
            return f"Set the default wave output volume to {percentage}%."
        except (AttributeError, OSError):
            return "This Windows audio feature is not available on the current system."

    return None


def _system_status() -> str:
    import socket

    if psutil is None:
        return "System metrics unavailable: install the optional psutil package."

    network = "Network connection: unavailable."
    try:
        with socket.create_connection(("1.1.1.1", 443), timeout=2):
            network = "Network connection: reachable."
    except OSError:
        pass
    memory = psutil.virtual_memory()
    return (
        f"Operating system: {sys.platform} {os.environ.get('OS', '')}\n"
        f"Windows: {platform.release()} build {platform.version()}\n"
        f"Python: {sys.version.split()[0]}\n"
        f"Processor: {platform.processor() or 'Not reported'}\n"
        f"Computer: {os.environ.get('COMPUTERNAME', 'unknown')}\n"
        f"CPU: {psutil.cpu_percent(interval=0.1):.0f}% utilization "
        f"({psutil.cpu_count(logical=True) or 'unknown'} logical processors)\n"
        f"Memory: {memory.percent:.0f}% used "
        f"({memory.used / (1024 ** 3):.1f} / {memory.total / (1024 ** 3):.1f} GiB)\n"
        f"Disk: {psutil.disk_usage(Path.home().anchor or '.').percent:.0f}% used\n"
        f"Battery: {_battery_status()}\n"
        f"{network}"
    )


def _battery_status() -> str:
    try:
        battery = psutil.sensors_battery()
    except (OSError, AttributeError):
        return "unavailable"
    if battery is None:
        return "not present"
    charging = "charging" if battery.power_plugged else "on battery"
    return f"{battery.percent:.0f}% ({charging})"
