from __future__ import annotations

import logging
import os
import queue
import re
import sqlite3
import shutil
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from pathlib import Path

from config import (
    APP_DIR,
    DASHBOARD_HTML_PATH,
    ICON_PATH,
    LOGO_IMAGE_PATH,
    MODEL_CHECKPOINT_PATH,
    REFERENCE_IMAGE_PATH,
    LOG_PATH,
    ensure_app_dir,
)
from jarvis.ai_client import AIError, LocalLanguageModel
from jarvis.automation import run_command
from jarvis.storage import Storage
from jarvis.voice_input import VoiceInput
from jarvis.voice_output import VoiceOutput
from jarvis.notes_service import KnowledgeBase, MemoryCore, NotesService, ReminderService
from jarvis.system_monitor import SystemSnapshot, collect_system_snapshot
from jarvis.web_search import open_search
from jarvis.image_loader import ImageLoader
from jarvis.hud_graphics import draw_hud


BG = "#06142b"
PANEL = "#0b1c3a"
PANEL_LIGHT = "#11294c"
CYAN = "#61caff"
BLUE = "#4c84ff"
TEXT = "#dbeaff"
MUTED = "#8ea9ca"
GREEN = "#53e0a0"
RED = "#ff627f"
_INSTANCE_MUTEX = None


class JarvisApp:
    def __init__(self, root: tk.Tk) -> None:
        ensure_app_dir()
        logging.basicConfig(
            filename=LOG_PATH,
            level=logging.WARNING,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )
        self.root = root
        self.root.title("JARVIS | Personal AI")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.ui_scale = min(1.5, max(1.0, screen_width / 1920))
        try:
            self.root.tk.call("tk", "scaling", 1.333 * self.ui_scale)
        except tk.TclError:
            pass
        window_width = min(3200, max(1120, int(screen_width * 0.88)))
        window_height = min(1800, max(680, int(screen_height * 0.86)))
        window_x = max(0, (screen_width - window_width) // 2)
        window_y = max(0, (screen_height - window_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        self.root.minsize(1120, 680)
        self.root.configure(bg=BG)
        if ICON_PATH.is_file():
            try:
                self.root.iconbitmap(str(ICON_PATH))
            except tk.TclError:
                logging.warning("The JARVIS application icon could not be loaded.")
        self.storage = Storage(APP_DIR / "jarvis.sqlite3")
        self.local_model = LocalLanguageModel(MODEL_CHECKPOINT_PATH)
        self.model_ready = self.local_model.is_trained
        self.model_training = False
        self.training_stop = threading.Event()
        self.image_loader = ImageLoader()
        self.logo_icon = self.image_loader.load(LOGO_IMAGE_PATH, 64, 64)
        self.logo_orb = self.image_loader.load(LOGO_IMAGE_PATH, 144, 144)
        self.logo_about = self.image_loader.load(LOGO_IMAGE_PATH, 240, 240)
        if self.logo_icon is not None:
            try:
                self.root.iconphoto(True, self.logo_icon)
            except tk.TclError:
                logging.warning("The JARVIS logo could not be used as the window icon.")
        self.reference_image = self.image_loader.load(REFERENCE_IMAGE_PATH, 860, 740)
        self.notes_service = NotesService(self.storage)
        self.reminder_service = ReminderService(self.storage)
        self.memory_core = MemoryCore(self.storage)
        self.knowledge_base = KnowledgeBase(self.storage)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.voice_output = VoiceOutput(on_done=lambda: self.events.put(("spoken", None)))
        self.voice_input = VoiceInput()
        self.messages: list[dict[str, str]] = []
        self.listening = False
        self.listen_cancel: threading.Event | None = None
        self.busy = False
        self.speaking = False
        self.animation_phase = 0
        self.current_page = ""
        self.system_snapshot: SystemSnapshot | None = None
        self.cpu_history: list[float] = []
        self.system_refresh_pending = False
        self.search_results: list[str] = []
        self.settings = self.storage.get_settings()
        self.model_ready = self.local_model.is_trained
        self.animation_enabled = bool(self.settings.get("animations", True))
        saved_quality = str(self.settings.get("graphics_quality", "High"))
        self.graphics_quality = (
            "High" if screen_width >= 2560 and saved_quality == "Balanced"
            else saved_quality
        )
        self.ai_error = False
        self.typing_visible = False
        self.stream_in_progress = False
        self._build_style()
        self._build_ui()
        self.root.bind("<Configure>", self._resize_visual_canvases, add="+")
        self.root.after_idle(self._resize_visual_canvases)
        self.root.after(120, self._enable_dark_titlebar)
        self._load_history()
        self._update_voice_status()
        self._animate()
        self._poll_events()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Jarvis.TEntry", fieldbackground=PANEL_LIGHT, foreground=TEXT,
            insertcolor=TEXT, bordercolor="#254570", lightcolor="#254570",
            darkcolor="#254570", padding=8,
        )
        style.configure(
            "Jarvis.TCheckbutton", background=PANEL, foreground=TEXT,
            focuscolor=PANEL, indicatorcolor=PANEL_LIGHT,
        )
        style.map(
            "Jarvis.TCheckbutton", background=[("active", PANEL)],
            foreground=[("active", CYAN)],
        )
        style.configure(
            "TCombobox", fieldbackground=PANEL_LIGHT,
            background=PANEL_LIGHT, foreground=TEXT, arrowcolor=CYAN,
            bordercolor="#254570", lightcolor="#254570",
            darkcolor="#254570", padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PANEL_LIGHT)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", "#1c4d80")],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "Jarvis.Vertical.TScrollbar", background="#193c66",
            troughcolor=BG, bordercolor=BG, arrowcolor=CYAN,
        )

    def _enable_dark_titlebar(self) -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            value = ctypes.c_int(1)
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = (
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
            )
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long
            for attribute in (20, 19):
                if dwm.DwmSetWindowAttribute(
                    ctypes.c_void_p(self.root.winfo_id()), attribute,
                    ctypes.byref(value), ctypes.sizeof(value),
                ) == 0:
                    break
        except (AttributeError, OSError, ValueError):
            logging.debug("Windows dark title-bar styling is unavailable.")

    def _update_clock(self) -> None:
        if not hasattr(self, "clock_label"):
            return
        now = datetime.now().astimezone()
        self.clock_label.configure(text=f"{now:%I:%M:%S %p}   ·   {now:%a, %b %d}")
        self.root.after(1000, self._update_clock)

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=PANEL, highlightbackground="#1a3652", highlightthickness=1)
        header.pack(fill="x", padx=8, pady=(7, 5))
        brand = tk.Frame(header, bg=PANEL)
        brand.pack(side="left")
        if self.logo_icon is not None:
            tk.Label(brand, image=self.logo_icon, bg=PANEL).pack(side="left", padx=(0, 8))
        else:
            tk.Label(brand, text="◉", fg=CYAN, bg=PANEL, font=("Segoe UI", 25, "bold")).pack(side="left", padx=(0, 8))
        brand_text = tk.Frame(brand, bg=PANEL)
        brand_text.pack(side="left")
        tk.Label(brand_text, text="JARVIS AI", fg=TEXT, bg=PANEL, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(brand_text, text="Your Personal AI Assistant", fg=MUTED, bg=PANEL, font=("Segoe UI", 8)).pack(anchor="w")
        tk.Label(
            header, text="T H I N K    •    A S S I S T    •    A U T O M A T E",
            fg=CYAN, bg=PANEL, font=("Segoe UI", 8),
        ).pack(side="left", expand=True)
        controls = tk.Frame(header, bg=PANEL)
        controls.pack(side="right")
        self.clock_label = tk.Label(controls, text="", fg=TEXT, bg=PANEL, font=("Segoe UI", 9, "bold"))
        self.clock_label.pack(side="left", padx=(0, 12))
        self._update_clock()
        tk.Label(controls, text="●", fg=GREEN, bg=PANEL, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 3))
        tk.Label(controls, text="READY", fg=GREEN, bg=PANEL, font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 10))
        self._button(controls, "Help", self._show_help, compact=True).pack(side="left", padx=3)
        self._button(controls, "About", self._show_about, compact=True).pack(side="left", padx=3)
        self._button(controls, "⛶", self._toggle_fullscreen, compact=True).pack(side="left", padx=3)
        self._button(controls, "—", self.root.iconify, compact=True).pack(side="left", padx=3)
        self._button(controls, "□", self._toggle_maximize, compact=True).pack(side="left", padx=3)
        self._button(controls, "×", self._close, compact=True, danger=True).pack(side="left", padx=3)

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.sidebar = tk.Frame(shell, bg=PANEL, width=int(154 * self.ui_scale), highlightbackground="#1a3652", highlightthickness=1)
        self.sidebar.pack(side="left", fill="y", padx=(0, 6))
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="WORKSPACE", fg=MUTED, bg=PANEL, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(14, 8))
        nav_items = (
            ("Home", "Home"),
            ("AI Chat", "AI Chat"),
            ("My AI Model", "Model"),
            ("Voice Control", "Voice Control"),
            ("Applications", "Applications"),
            ("Web & Search", "Web Search"),
            ("Notes & Reminders", "Notes"),
            ("Memory & Knowledge", "Memory"),
            ("System Information", "System Info"),
            ("Automation", "Automation"),
            ("Settings", "Settings"),
        )
        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_icons = {
            "Home": "⌂", "AI Chat": "▤", "Voice Control": "♩",
            "Applications": "▦", "Web Search": "◎", "Notes": "▧",
            "Memory": "◈", "Model": "⌘",
            "System Info": "▣", "Automation": "⚙", "Settings": "⚙",
        }
        for label, page in nav_items:
            button = tk.Button(
                self.sidebar, text=f"  {self.nav_icons.get(page, '○')}  {label}", anchor="w",
                command=lambda selected=page: self._show_page(selected),
                bg=PANEL, fg=TEXT, activebackground=PANEL_LIGHT, activeforeground=CYAN,
                relief="flat", bd=0, padx=10, pady=9, cursor="hand2",
                font=("Segoe UI", 9), highlightthickness=1,
                highlightbackground=PANEL, highlightcolor=CYAN,
            )
            button.pack(fill="x", padx=7, pady=2)
            button.bind("<Enter>", lambda _event, target=button: self._transition_button(target, PANEL_LIGHT))
            button.bind(
                "<Leave>",
                lambda _event, target=button, key=page: self._transition_button(
                    target, "#173960" if self.current_page == key else PANEL
                ),
            )
            self.nav_buttons[page] = button
        self.overview = tk.Frame(shell, bg=PANEL, width=int(176 * self.ui_scale), highlightbackground="#1a3652", highlightthickness=1)
        self.overview.pack(side="left", fill="y", padx=(0, 6))
        self.overview.pack_propagate(False)
        self._build_system_overview()
        self.center = tk.Frame(shell, bg=BG)
        self.center.pack(side="left", fill="both", expand=True)
        self.pages: dict[str, tk.Frame] = {}
        self._build_chat_page()
        # The reference command-center combines the home dashboard and live chat.
        self.pages["Home"] = self.pages["AI Chat"]
        self._build_notes_page()
        self._build_memory_page()
        self._build_model_page()
        self._build_search_page()
        self._build_apps_page()
        self._build_system_page()
        self._build_automation_page()

        self.dashboard = tk.Frame(shell, bg=BG, width=int(264 * self.ui_scale))
        self.dashboard.pack(side="right", fill="y", padx=(8, 0))
        self.dashboard.pack_propagate(False)
        self._build_dashboard()
        self.header_status = self.dashboard_model_status
        self._refresh_model_status()

        footer = tk.Frame(self.root, bg=PANEL, highlightbackground="#1a3652", highlightthickness=1)
        footer.pack(fill="x", padx=8, pady=(0, 5))
        self.ai_status = tk.Label(
            footer, text="● LOCAL MODEL TRAINED" if self.model_ready else "● LOCAL MODEL NOT TRAINED",
            fg=MUTED, bg=PANEL, font=("Segoe UI", 8),
        )
        self.ai_status.pack(side="left")
        self.mic_status = tk.Label(footer, text="● Mic idle", fg=MUTED, bg=PANEL, font=("Segoe UI", 8))
        self.mic_status.pack(side="left", padx=14)
        self.tts_status = tk.Label(footer, text="● Speech engine starting", fg=MUTED, bg=PANEL, font=("Segoe UI", 8))
        self.tts_status.pack(side="left")
        tk.Label(footer, text="MICROPHONE STAYS OFF UNTIL YOU START LISTENING", fg=MUTED, bg=PANEL, font=("Segoe UI", 7, "bold")).pack(side="right", padx=8)

        self._show_page(str(self.settings.get("startup_page", "Home")))
        self.root.bind("<F11>", lambda _event: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda _event: self.root.attributes("-fullscreen", False))
        self.root.bind_all("<Control-l>", lambda _event: self.input.focus_set())
        self.root.bind_all("<Control-n>", lambda _event: self._new_note())
        self.root.bind_all("<Control-Shift-c>", lambda _event: self._clear_chat())
        self._refresh_notes()
        self._refresh_reminders()
        self._refresh_searches()
        self._refresh_shortcuts()
        self._refresh_system()
        self._refresh_dashboard()

    def _build_home_page(self) -> None:
        page = self._new_page("Home", "JARVIS AI CONTROL CENTER")
        tk.Label(
            page, text="LOCAL NEURAL SYSTEM  /  SECURE DESKTOP INTERFACE",
            fg=CYAN, bg=BG, wraplength=700, justify="left",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(0, 3))
        tk.Label(
            page,
            text="Your personal command center is online. Explore local tools, system telemetry, and the JARVIS learning core.",
            fg=MUTED, bg=BG, wraplength=700, justify="left",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 6))
        self.home_core = tk.Canvas(
            page, height=340, bg="#07162f", highlightthickness=1,
            highlightbackground="#256dad",
        )
        self.home_core.pack(fill="x", pady=5)
        self.home_core.configure(cursor="hand2")
        self.home_core.bind("<Button-1>", lambda _event: self._show_page("AI Chat"))
        tk.Label(
            page, text="✦  JARVIS HOLOGRAPHIC CORE  ·  CLICK TO OPEN CHAT  ·  LOCAL MODEL",
            fg=CYAN, bg=BG, font=("Segoe UI", 8, "bold"),
        ).pack(anchor="center", pady=(0, 6))
        quick = tk.Frame(page, bg=BG)
        quick.pack(fill="x", pady=8)
        for title, action in (
            ("Start a chat", lambda: self._show_page("AI Chat")),
            ("Create a note", self._new_note),
            ("Search the web", lambda: self._show_page("Web Search")),
            ("System dashboard", lambda: self._show_page("System Info")),
        ):
            card = tk.Frame(quick, bg=PANEL, highlightbackground="#1a3652", highlightthickness=1)
            card.pack(side="left", fill="both", expand=True, padx=4)
            self._button(card, title, action, primary=True).pack(fill="x", padx=8, pady=12)
        summary = tk.Frame(page, bg=PANEL)
        summary.pack(fill="both", expand=True, pady=(8, 0))
        self.home_summary = tk.Label(
            summary, text="Loading recent activity…", fg=MUTED, bg=PANEL,
            justify="left", anchor="nw", font=("Segoe UI", 9),
        )
        self.home_summary.pack(fill="both", expand=True, padx=14, pady=12)

    def _build_chat_page(self) -> None:
        page = tk.Frame(self.center, bg=BG)
        self.pages["AI Chat"] = page
        self.pages["Voice Control"] = page
        visual = tk.Frame(page, bg=BG)
        visual.pack(fill="x")
        self.canvas = tk.Canvas(visual, height=252, bg=BG, highlightthickness=1,
                                highlightbackground="#24537f")
        self.canvas.pack(fill="x", expand=False)
        self.canvas.configure(cursor="hand2")
        self.canvas.bind("<Button-1>", lambda _event: self.input.focus_set() if hasattr(self, "input") else None)
        statebar = tk.Frame(visual, bg=PANEL, highlightbackground="#24537f", highlightthickness=1)
        statebar.pack(fill="x", pady=(0, 5))
        tk.Label(statebar, text="◉  CORE STATUS", fg=CYAN, bg=PANEL,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=(10, 6), pady=5)
        self.state_label = tk.Label(statebar, text="SYSTEM READY", fg=CYAN, bg=PANEL,
                                    font=("Segoe UI", 8, "bold"))
        self.state_label.pack(side="left", pady=5)
        tk.Label(statebar, text="J.A.R.V.I.S.  /  INTERACTIVE COMMAND CENTER",
                 fg=MUTED, bg=PANEL, font=("Segoe UI", 7, "bold")).pack(side="right", padx=10)

        chat_frame = tk.Frame(page, bg=PANEL, highlightbackground="#24537f", highlightthickness=1)
        chat_frame.pack(fill="both", expand=True, pady=(0, 0))
        self.chat = tk.Text(
            chat_frame, wrap="word", state="disabled", bg=PANEL, fg=TEXT,
            relief="flat", padx=14, pady=12, font=("Segoe UI", 9),
            spacing1=4, spacing3=8, selectbackground="#1c4d80",
        )
        scrollbar = ttk.Scrollbar(
            chat_frame, orient="vertical", command=self.chat.yview,
            style="Jarvis.Vertical.TScrollbar",
        )
        self.chat.configure(yscrollcommand=scrollbar.set)
        self.chat.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y")
        self.chat.tag_configure("user", foreground=CYAN, font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("assistant", foreground=GREEN, font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("body", foreground=TEXT)
        self.chat.tag_configure(
            "user_body", foreground=TEXT, background="#16355b",
            lmargin1=10, lmargin2=10, rmargin=18, spacing1=5, spacing3=5,
        )
        self.chat.tag_configure(
            "assistant_body", foreground=TEXT, background="#102747",
            lmargin1=10, lmargin2=10, rmargin=18, spacing1=5, spacing3=5,
        )
        self.chat.tag_configure("system", foreground=MUTED, font=("Segoe UI", 9, "italic"))
        self.chat.tag_configure("timestamp", foreground=MUTED, font=("Segoe UI", 8))
        self._append_message(
            "JARVIS",
            "JARVIS LOCAL AI READY\nThe original model starts untrained. Open My AI Model to train it on a small, user-approved local text file or the clearly labelled synthetic demo. Local commands and saved knowledge work independently.",
            "assistant",
            persist=False,
        )
        chips = tk.Frame(page, bg=BG)
        chips.pack(fill="x", pady=(4, 3))
        for label, action in (
            ("Open Notepad", lambda: self._launch_app("notepad")),
            ("System Info", lambda: self._show_page("System Info")),
            ("Search Web", lambda: self._show_page("Web Search")),
            ("Create Note", self._new_note),
        ):
            self._button(chips, label, action, compact=True).pack(side="left", padx=(0, 5))

        composer = tk.Frame(page, bg=PANEL, highlightbackground="#2878b5", highlightthickness=1)
        composer.pack(fill="x", pady=(0, 0))
        mic_area = tk.Frame(composer, bg=PANEL)
        mic_area.pack(side="left", padx=(7, 5), pady=3)
        self.mic_button = tk.Button(
            mic_area, text="🎙", command=self._toggle_listening, width=3, height=1,
            bg="#12355d", fg=CYAN, activebackground="#1c4d80", activeforeground=TEXT,
            relief="flat", bd=0, cursor="hand2", font=("Segoe UI Symbol", 16, "bold"),
            highlightthickness=1, highlightbackground=CYAN,
        )
        self.mic_button.pack(side="left")
        self.mic_button.bind("<Enter>", lambda _event: self._transition_button(self.mic_button, "#1c4d80"))
        self.mic_button.bind("<Leave>", lambda _event: self._transition_button(self.mic_button, "#12355d"))
        self.voice_dial_label = tk.Label(mic_area, text="MIC OFF", fg=MUTED, bg=PANEL,
                                         font=("Segoe UI", 7, "bold"))
        self.voice_dial_label.pack(side="left", padx=6)
        self._button(composer, "⚙", self._open_settings, compact=True).pack(side="right", padx=2, pady=5)
        self.send_button = self._button(composer, "➤", self._send, primary=True, compact=True)
        self.send_button.pack(side="right", padx=(2, 6), pady=5)
        self.input = ttk.Entry(composer, style="Jarvis.TEntry", font=("Segoe UI", 9))
        self.input.pack(side="left", fill="x", expand=True, padx=7, pady=6, ipady=2)
        self.input.bind("<Return>", lambda _event: self._send())
        controls = tk.Frame(page, bg=BG)
        controls.pack(fill="x", pady=(5, 0))
        self.stop_button = self._button(
            controls, "■  Stop Speaking", self._stop_speaking, compact=True,
        )
        self.stop_button.pack(side="left", padx=4)
        self._button(controls, "▤  Clear Chat", self._clear_chat, compact=True).pack(side="left", padx=4)
        self._button(controls, "⚙  Settings", self._open_settings, compact=True).pack(side="left", padx=4)
        self._button(controls, "⌕  Web Search", lambda: self._show_page("Web Search"), compact=True).pack(side="right", padx=2)

    def _build_dashboard(self) -> None:
        actions_panel = self._dashboard_panel("ϟ  QUICK ACTIONS")
        quick_actions = tk.Frame(actions_panel, bg=PANEL)
        quick_actions.pack(fill="x", padx=5, pady=(0, 5))
        for index, (label, callback) in enumerate((
            ("▤  Notepad", lambda: self._launch_app("notepad")),
            ("▦  Calculator", lambda: self._launch_app("calculator")),
            ("◈  Paint", lambda: self._launch_app("paint")),
            ("◎  Browser", lambda: self._launch_app("browser")),
            ("⌕  Search Web", lambda: self._show_page("Web Search")),
            ("✎  Create Note", self._new_note),
            ("▣  Open Folder", self._open_folder),
            ("▥  System Info", lambda: self._show_page("System Info")),
            ("✧  More Tools", lambda: self._show_page("Automation")),
        )):
            self._button(
                quick_actions, label, callback, compact=True
            ).grid(row=index // 3, column=index % 3, sticky="ew", padx=2, pady=2)
        for column in range(3):
            quick_actions.grid_columnconfigure(column, weight=1)

        model_panel = self._dashboard_panel("◉  LOCAL MODEL STATUS")
        self.dashboard_model_name = tk.Label(
            model_panel, text="JARVIS Byte-Bigram Neural LM · v1",
            fg=TEXT, bg=PANEL, font=("Segoe UI", 8), anchor="w",
        )
        self.dashboard_model_name.pack(fill="x", padx=9, pady=(0, 2))
        self.dashboard_model_status = tk.Label(
            model_panel, text="Checking local checkpoint…", fg=MUTED, bg=PANEL,
            font=("Segoe UI", 8, "bold"), anchor="w",
        )
        self.dashboard_model_status.pack(fill="x", padx=9, pady=(0, 4))
        self.dashboard_model_metrics = tk.Label(
            model_panel, text="", fg=MUTED, bg=PANEL, font=("Segoe UI", 7), anchor="w",
        )
        self.dashboard_model_metrics.pack(fill="x", padx=9, pady=(0, 5))
        self._button(
            model_panel, "Open My AI Model", lambda: self._show_page("Model"),
            compact=True, primary=True,
        ).pack(fill="x", padx=7, pady=(0, 6))

        voice_panel = self._dashboard_panel("♬  VOICE & SPEECH")
        self.dashboard_mic = tk.Label(
            voice_panel, text="Microphone · idle", fg=MUTED, bg=PANEL,
            font=("Segoe UI", 8), anchor="w",
        )
        self.dashboard_mic.pack(fill="x", padx=9, pady=(0, 3))
        self.dashboard_tts = tk.Label(
            voice_panel, text="Speech engine · checking", fg=MUTED, bg=PANEL,
            font=("Segoe UI", 8), anchor="w",
        )
        self.dashboard_tts.pack(fill="x", padx=9, pady=(0, 7))

        reminder_panel = self._dashboard_panel("♧  UPCOMING REMINDERS")
        self.reminder_summary = tk.Label(
            reminder_panel, text="No upcoming reminders", fg=MUTED, bg=PANEL,
            wraplength=228, justify="left", font=("Segoe UI", 8),
        )
        self.reminder_summary.pack(fill="x", padx=10, pady=(0, 7))

    def _build_system_overview(self) -> None:
        tk.Label(
            self.overview, text="▣  SYSTEM OVERVIEW", fg=CYAN, bg=PANEL,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=9, pady=(10, 8))
        self.dashboard_os = self._system_info_row(self.overview, "WINDOWS", "Reading…")
        self.dashboard_processor = self._system_info_row(self.overview, "PROCESSOR", "Reading…")
        self.dashboard_cpu = self._system_info_row(self.overview, "CPU LOAD", "Reading…")
        self.dashboard_memory = self._system_info_row(self.overview, "MEMORY", "Reading…")
        self.dashboard_disk = self._system_info_row(self.overview, "DISK", "Reading…")
        self.dashboard_battery = self._system_info_row(self.overview, "BATTERY", "Checking…")
        tk.Frame(self.overview, bg="#1a3a60", height=1).pack(fill="x", padx=9, pady=8)
        tk.Label(
            self.overview, text="LIVE UTILIZATION", fg=MUTED, bg=PANEL,
            font=("Segoe UI", 7, "bold"),
        ).pack(anchor="w", padx=9, pady=(0, 4))
        self.system_meter_canvases: dict[str, tk.Canvas] = {}
        for title, key in (("CPU", "cpu"), ("RAM", "memory"), ("DISK", "disk")):
            meter = tk.Frame(self.overview, bg=PANEL)
            meter.pack(fill="x", padx=9, pady=3)
            tk.Label(meter, text=title, fg=MUTED, bg=PANEL,
                     font=("Segoe UI", 7, "bold")).pack(anchor="w")
            graph = tk.Canvas(meter, height=17, bg="#0b1c39", highlightthickness=0)
            graph.pack(fill="x", pady=(2, 0))
            self.system_meter_canvases[key] = graph
        tk.Frame(self.overview, bg="#1a3a60", height=1).pack(fill="x", padx=9, pady=9)
        tk.Label(
            self.overview, text="“I’m always here to\nhelp you.”\n\n— JARVIS",
            fg="#9fc7e5", bg=PANEL, justify="center",
            font=("Segoe UI", 9, "italic"),
        ).pack(side="bottom", fill="x", padx=8, pady=12)

    def _dashboard_panel(self, title: str) -> tk.Frame:
        panel = tk.Frame(
            self.dashboard, bg=PANEL,
            highlightbackground="#21436a", highlightthickness=1,
        )
        panel.pack(fill="x", pady=(0, 7))
        tk.Label(
            panel, text=title, fg=CYAN, bg=PANEL,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(7, 5))
        tk.Frame(panel, bg="#2878b5", height=1).pack(fill="x", padx=8, pady=(0, 4))
        return panel

    def _system_info_row(self, parent: tk.Frame, title: str, initial: str) -> tk.Label:
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", padx=10, pady=2)
        tk.Label(row, text=title, fg=MUTED, bg=PANEL, font=("Segoe UI", 8)).pack(side="left")
        value = tk.Label(
            row, text=initial, fg=TEXT, bg=PANEL, font=("Segoe UI", 7),
            anchor="e", width=12,
        )
        value.pack(side="right")
        return value

    def _dashboard_card(self, title: str, initial: str) -> tk.Label:
        frame = tk.Frame(self.dashboard, bg=PANEL_LIGHT, highlightbackground="#1a3652", highlightthickness=1)
        frame.pack(fill="x", padx=9, pady=3)
        tk.Label(frame, text=title, fg=MUTED, bg=PANEL_LIGHT, font=("Segoe UI", 7, "bold")).pack(anchor="w", padx=8, pady=(5, 0))
        value = tk.Label(frame, text=initial, fg=TEXT, bg=PANEL_LIGHT, font=("Segoe UI", 8), wraplength=174, justify="left")
        value.pack(anchor="w", padx=8, pady=(1, 5))
        return value

    def _section_label(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, fg=MUTED, bg=PANEL, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

    def _show_page(self, name: str) -> None:
        if name == "Settings":
            self._open_settings()
            return
        page = self.pages.get(name)
        if page is None:
            return
        for candidate in set(self.pages.values()):
            candidate.pack_forget()
        page.pack(fill="both", expand=True)
        self.current_page = name
        for page_name, button in self.nav_buttons.items():
            active = page_name == name or (name == "Voice Control" and page_name == "AI Chat")
            label = "System Information" if page_name == "System Info" else page_name
            button.configure(
                text=f"  {'●' if active else self.nav_icons.get(page_name, '○')}  {label}",
                bg="#173960" if active else PANEL,
                fg=CYAN if active else TEXT,
                highlightbackground="#3e7dea" if active else PANEL,
            )
        if name == "System Info":
            self._refresh_system()
        elif name == "Notes":
            self._refresh_notes()
            self._refresh_reminders()
        elif name == "Memory":
            self._refresh_memory_page()
        elif name == "Applications":
            self._refresh_shortcuts()
        elif name == "Web Search":
            self._refresh_searches()

    def _toggle_maximize(self) -> None:
        try:
            is_zoomed = self.root.state() == "zoomed"
            self.root.state("normal" if is_zoomed else "zoomed")
        except tk.TclError:
            logging.warning("The window manager does not support maximize/restore.")

    def _refresh_home_summary(self) -> None:
        if not hasattr(self, "home_summary"):
            return
        try:
            notes = self.storage.get_notes()[:3]
            reminders = self.reminder_service.upcoming()[:3]
            timestamps = self.storage.message_timestamps(limit=1)
            last_chat = datetime.fromisoformat(timestamps[-1]).strftime("%b %d, %H:%M") if timestamps else "No saved conversations"
            note_lines = [f"  • {item['title']}" for item in notes] or ["  • No notes yet"]
            reminder_lines = [
                f"  • {item['due_at']} — {item['title']}" for item in reminders
            ] or ["  • No upcoming reminders"]
            lines = [
                "RECENT ACTIVITY",
                f"Last conversation: {last_chat}",
                "Recent notes:",
                *note_lines,
                "Upcoming reminders:",
                *reminder_lines,
            ]
            self.home_summary.configure(text="\n".join(lines))
        except (sqlite3.Error, ValueError):
            logging.exception("Could not load home activity summary")
            self.home_summary.configure(text="Recent activity is currently unavailable.")

    def _show_reference_image(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("JARVIS interface reference")
        dialog.configure(bg=BG)
        dialog.transient(self.root)
        dialog.geometry("900x820")
        if self.reference_image is None:
            tk.Label(
                dialog,
                text="The optional reference image is unavailable.\n"
                     "Place reference_ui.png in assets/ui_gui_images.",
                fg=MUTED, bg=BG, justify="center", font=("Segoe UI", 10),
            ).pack(fill="both", expand=True, padx=20, pady=20)
        else:
            tk.Label(
                dialog, image=self.reference_image, bg=BG,
                text="Design reference only — JARVIS controls remain native, functional widgets.",
                compound="top", fg=MUTED, font=("Segoe UI", 9),
            ).pack(fill="both", expand=True, padx=12, pady=12)
        self._button(dialog, "Close", dialog.destroy, primary=True).pack(pady=(0, 10))
        dialog.focus_set()

    def _toggle_fullscreen(self) -> None:
        value = bool(self.root.attributes("-fullscreen"))
        self.root.attributes("-fullscreen", not value)

    def _launch_app(self, app_name: str) -> None:
        names = {
            "notepad": "Notepad",
            "calculator": "Calculator",
            "calc": "Calculator",
            "paint": "Paint",
            "browser": "the default browser",
        }
        name = names.get(app_name.lower(), app_name)
        result = run_command(f"open {app_name}") if app_name.lower() != "browser" else None
        if app_name.lower() == "browser":
            import webbrowser

            try:
                opened = webbrowser.open("about:blank", new=2)
            except Exception:
                logging.exception("Could not open the default browser")
                opened = False
            result = "Opened the default browser." if opened else "Windows couldn't open the default browser."
        if result is None:
            result = f"Application '{name}' is not on the approved launch list."
        self._show_action_result(result)

    def _show_action_result(self, message: str) -> None:
        if hasattr(self, "chat"):
            self._append_message("JARVIS", message, "assistant", persist=False)
        self.state_label.configure(text="SYSTEM READY", fg=CYAN)

    def _open_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose a folder to open", parent=self.root)
        if not folder:
            return
        try:
            if not hasattr(os, "startfile"):
                raise OSError("This action requires Windows.")
            os.startfile(folder)
            self._show_action_result(f"Opened folder: {folder}")
        except OSError as error:
            messagebox.showerror("Could not open folder", f"Windows couldn't open that folder.\n{error}", parent=self.root)

    def _prompt_website(self) -> None:
        from tkinter import simpledialog

        address = simpledialog.askstring("Open website", "Enter a website URL:", parent=self.root)
        if address:
            from jarvis.web_search import open_website

            self._show_action_result(open_website(address))

    def _start_file_search(self) -> None:
        self.input.delete(0, "end")
        self.input.insert(0, "search files")
        self._send()

    def _perform_search(self) -> None:
        query = self.web_query.get().strip()
        if not query:
            messagebox.showinfo("Web search", "Enter a search query first.", parent=self.root)
            return
        try:
            self.storage.add_search(query)
            result = open_search(query)
        except sqlite3.Error:
            logging.exception("Could not save search history")
            from jarvis.web_search import open_search

            result = open_search(query)
        self._refresh_searches()
        self._show_action_result(result)

    def _repeat_search(self, _event=None) -> None:
        selection = self.search_list.curselection()
        if not selection:
            return
        query = self.search_list.get(selection[0])
        self.web_query.delete(0, "end")
        self.web_query.insert(0, query)
        self._perform_search()

    def _refresh_searches(self) -> None:
        if not hasattr(self, "search_list"):
            return
        self.search_results = self.storage.get_searches()
        self.search_list.delete(0, "end")
        for query in self.search_results:
            self.search_list.insert("end", query)

    def _build_notes_refresh(self) -> None:
        self._refresh_notes()
        self._refresh_reminders()

    def _delete_reminder(self) -> None:
        selection = self.reminders_list.curselection()
        if not selection:
            messagebox.showinfo("Reminder", "Select a reminder first.", parent=self.root)
            return
        reminder = self.reminder_items[selection[0]]
        if not messagebox.askyesno(
            "Delete reminder",
            f"Permanently delete '{reminder['title']}'?",
            parent=self.root,
        ):
            return
        try:
            self.reminder_service.delete(int(reminder["id"]))
        except sqlite3.Error:
            logging.exception("Could not delete reminder")
            messagebox.showerror("Reminder", "JARVIS couldn't delete that reminder.", parent=self.root)
            return
        self._refresh_reminders()

    def _refresh_notes(self) -> None:
        if not hasattr(self, "notes_list"):
            return
        try:
            self.note_items = self.notes_service.search(self.note_search.get())
        except sqlite3.Error:
            logging.exception("Could not load notes")
            return
        self.notes_list.delete(0, "end")
        for note in self.note_items:
            self.notes_list.insert("end", str(note["title"]))

    def _select_note(self, _event=None) -> None:
        selection = self.notes_list.curselection()
        if not selection:
            return
        note = self.note_items[selection[0]]
        self.current_note_id = int(note["id"])
        self.note_title.delete(0, "end")
        self.note_title.insert(0, str(note["title"]))
        self.note_body.delete("1.0", "end")
        self.note_body.insert("1.0", str(note["body"]))
        self.note_timestamp.configure(
            text=f"Created {note['created_at']} · Modified {note['updated_at']}"
        )

    def _new_note(self) -> None:
        self._show_page("Notes")
        self.current_note_id = None
        self.note_title.delete(0, "end")
        self.note_body.delete("1.0", "end")
        self.note_timestamp.configure(text="New note")
        self.note_title.focus_set()

    def _save_note(self) -> None:
        try:
            note_id = getattr(self, "current_note_id", None)
            saved_id = self.notes_service.save(
                self.note_title.get(),
                self.note_body.get("1.0", "end"),
                note_id,
            )
        except ValueError as error:
            messagebox.showerror("Note not saved", str(error), parent=self.root)
            return
        except sqlite3.Error:
            logging.exception("Could not save note")
            messagebox.showerror("Note not saved", "JARVIS couldn't write this note to local storage.", parent=self.root)
            return
        self.current_note_id = saved_id
        self._refresh_notes()
        self._refresh_home_summary()

    def _delete_note(self) -> None:
        note_id = getattr(self, "current_note_id", None)
        if note_id is None:
            messagebox.showinfo("Delete note", "Select a saved note first.", parent=self.root)
            return
        if not messagebox.askyesno("Delete note", "Permanently delete this note?", parent=self.root):
            return
        try:
            self.notes_service.delete(note_id)
        except sqlite3.Error:
            logging.exception("Could not delete note")
            messagebox.showerror("Delete note", "JARVIS couldn't delete this note.", parent=self.root)
            return
        self.current_note_id = None
        self.note_title.delete(0, "end")
        self.note_body.delete("1.0", "end")
        self.note_timestamp.configure(text="Not saved")
        self._refresh_notes()
        self._refresh_home_summary()

    def _add_reminder(self) -> None:
        try:
            reminder_id = getattr(self, "current_reminder_id", None)
            details = self.reminder_details.get().strip()
            if details == "Details (optional)":
                details = ""
            self.reminder_service.create(
                self.reminder_title.get(), self.reminder_due.get(),
                details, reminder_id,
            )
        except ValueError as error:
            messagebox.showerror("Reminder not saved", str(error), parent=self.root)
            return
        except sqlite3.Error:
            logging.exception("Could not save reminder")
            messagebox.showerror("Reminder not saved", "JARVIS couldn't save the reminder locally.", parent=self.root)
            return
        self.reminder_title.delete(0, "end")
        self.reminder_due.delete(0, "end")
        self.reminder_due.insert(0, "YYYY-MM-DD HH:MM")
        self.reminder_details.delete(0, "end")
        self.reminder_details.insert(0, "Details (optional)")
        self.current_reminder_id = None
        self._refresh_reminders()
        self._refresh_home_summary()

    def _refresh_reminders(self) -> None:
        if not hasattr(self, "reminders_list"):
            return
        try:
            self.reminder_items = self.storage.get_reminders()
        except sqlite3.Error:
            logging.exception("Could not load reminders")
            return
        self.reminders_list.delete(0, "end")
        for reminder in self.reminder_items:
            mark = "✓" if reminder["completed"] else "○"
            self.reminders_list.insert("end", f"{mark} {reminder['due_at']} — {reminder['title']}")
        upcoming = self.reminder_service.upcoming()
        short = [f"{item['due_at']} · {item['title']}" for item in upcoming[:3]]
        self.reminder_summary.configure(text="\n".join(short) if short else "No upcoming reminders")
        self._refresh_home_summary()

    def _edit_reminder(self) -> None:
        selection = self.reminders_list.curselection()
        if not selection:
            messagebox.showinfo("Reminder", "Select a reminder to edit.", parent=self.root)
            return
        reminder = self.reminder_items[selection[0]]
        self.current_reminder_id = int(reminder["id"])
        self.reminder_title.delete(0, "end")
        self.reminder_title.insert(0, str(reminder["title"]))
        self.reminder_due.delete(0, "end")
        self.reminder_due.insert(0, str(reminder["due_at"]))
        self.reminder_details.delete(0, "end")
        self.reminder_details.insert(0, str(reminder["details"]))
        self.reminder_title.focus_set()

    def _complete_reminder(self) -> None:
        selection = self.reminders_list.curselection()
        if not selection:
            messagebox.showinfo("Reminder", "Select a reminder first.", parent=self.root)
            return
        reminder = self.reminder_items[selection[0]]
        try:
            self.reminder_service.complete(int(reminder["id"]), not bool(reminder["completed"]))
        except sqlite3.Error:
            logging.exception("Could not update reminder")
            messagebox.showerror("Reminder", "JARVIS couldn't update that reminder.", parent=self.root)
            return
        self._refresh_reminders()

    def _refresh_shortcuts(self) -> None:
        if not hasattr(self, "shortcuts_list"):
            return
        try:
            self.shortcut_items = self.storage.get_shortcuts()
        except sqlite3.Error:
            logging.exception("Could not load application shortcuts")
            return
        self.shortcuts_list.delete(0, "end")
        for shortcut in self.shortcut_items:
            self.shortcuts_list.insert("end", f"{shortcut['name']}  ·  {shortcut['path']}")

    def _add_shortcut(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose an application executable",
            filetypes=(("Windows applications", "*.exe"), ("All files", "*.*")),
            parent=self.root,
        )
        if not path:
            return
        from tkinter import simpledialog

        default = Path(path).stem
        name = simpledialog.askstring("Application shortcut", "Shortcut name:", initialvalue=default, parent=self.root)
        if not name or not name.strip():
            return
        try:
            self.storage.save_shortcut(name.strip(), path)
        except sqlite3.Error:
            logging.exception("Could not save application shortcut")
            messagebox.showerror("Shortcut", "JARVIS couldn't save this shortcut.", parent=self.root)
            return
        self._refresh_shortcuts()

    def _remove_shortcut(self) -> None:
        selection = self.shortcuts_list.curselection()
        if not selection:
            messagebox.showinfo("Shortcut", "Select a shortcut to remove.", parent=self.root)
            return
        item = self.shortcut_items[selection[0]]
        if not messagebox.askyesno("Remove shortcut", f"Remove '{item['name']}' from JARVIS?", parent=self.root):
            return
        try:
            self.storage.delete_shortcut(int(item["id"]))
        except sqlite3.Error:
            logging.exception("Could not remove application shortcut")
            messagebox.showerror("Shortcut", "JARVIS couldn't remove that shortcut.", parent=self.root)
            return
        self._refresh_shortcuts()

    def _launch_selected_shortcut(self, _event=None) -> None:
        selection = self.shortcuts_list.curselection()
        if not selection:
            return
        path = Path(str(self.shortcut_items[selection[0]]["path"]))
        if not path.is_file():
            messagebox.showerror("Application unavailable", f"This shortcut target no longer exists:\n{path}", parent=self.root)
            return
        try:
            subprocess.Popen([str(path)], shell=False, cwd=str(path.parent))
        except OSError as error:
            messagebox.showerror("Application unavailable", f"Windows couldn't start the selected application.\n{error}", parent=self.root)

    def _refresh_system(self) -> None:
        if self.system_refresh_pending:
            return
        self.system_refresh_pending = True
        threading.Thread(target=self._system_worker, daemon=True).start()

    def _system_worker(self) -> None:
        try:
            snapshot = collect_system_snapshot()
            self.events.put(("system", snapshot))
            microphone_status = "Offline transcription not implemented"
            self.events.put(("system_voice", microphone_status))
        except Exception:
            logging.exception("Could not collect system information")
            self.events.put(("system_error", "System metrics are currently unavailable."))

    def _render_system(self, snapshot: SystemSnapshot) -> None:
        self.system_snapshot = snapshot
        if snapshot.cpu_percent is not None:
            self.cpu_history.append(snapshot.cpu_percent)
            self.cpu_history = self.cpu_history[-48:]
        def metric(value, suffix=""):
            return f"{value:.0f}{suffix}" if value is not None else "Unavailable"
        self.dashboard_os.configure(
            text=snapshot.operating_system.split(" (")[0][:13]
        )
        self.dashboard_processor.configure(
            text=snapshot.processor[:13] + ("…" if len(snapshot.processor) > 13 else "")
        )
        lines = [
            f"APPLICATION\nJARVIS AI 1.0.0 · Python {sys.version.split()[0]}",
            f"OPERATING SYSTEM\n{snapshot.operating_system}",
            f"PROCESSOR\n{snapshot.processor}",
            f"CPU UTILIZATION\n{metric(snapshot.cpu_percent, '%')}",
            f"MEMORY\n{metric(snapshot.memory_percent, '%')}  ·  "
            f"{snapshot.memory_used_gb:.1f} / {snapshot.memory_total_gb:.1f} GiB"
            if snapshot.memory_percent is not None else "MEMORY\nUnavailable",
            f"DISK\n{metric(snapshot.disk_percent, '%')}  ·  "
            f"{snapshot.disk_used_gb:.1f} / {snapshot.disk_total_gb:.1f} GiB"
            if snapshot.disk_percent is not None else "DISK\nUnavailable",
            f"BATTERY\n{snapshot.battery_percent:.0f}% · "
            f"{'Charging' if snapshot.battery_plugged else 'On battery'}"
            if snapshot.battery_percent is not None else "BATTERY\nNot present or unavailable",
        ]
        self.system_text.configure(state="normal")
        self.system_text.delete("1.0", "end")
        self.system_text.insert("1.0", "\n\n".join(lines))
        self.system_text.configure(state="disabled")
        self.system_refresh_pending = False
        self.dashboard_cpu.configure(text=metric(snapshot.cpu_percent, "%"))
        self.dashboard_memory.configure(
            text=metric(snapshot.memory_percent, "%")
        )
        self.dashboard_disk.configure(
            text=metric(snapshot.disk_percent, "%")
        )
        self.dashboard_battery.configure(
            text=(
                f"{snapshot.battery_percent:.0f}% · {'AC' if snapshot.battery_plugged else 'Battery'}"
                if snapshot.battery_percent is not None else "Not present"
            )
        )
        self._draw_system_meters({
            "cpu": snapshot.cpu_percent,
            "memory": snapshot.memory_percent,
            "disk": snapshot.disk_percent,
        })

    def _draw_system_meters(self, values: dict[str, float | None]) -> None:
        for key, canvas in getattr(self, "system_meter_canvases", {}).items():
            canvas.delete("all")
            width = max(canvas.winfo_width(), 90)
            height = max(canvas.winfo_height(), 14)
            canvas.create_rectangle(1, 3, width - 1, height - 3,
                                    outline="#20486e", fill="#0b1c39")
            for tick in range(1, 5):
                x = width * tick / 5
                canvas.create_line(x, 4, x, height - 4, fill="#142f52")
            value = values.get(key)
            if value is None:
                canvas.create_text(width - 5, height / 2, text="N/A", anchor="e",
                                   fill=MUTED, font=("Segoe UI", 7))
                continue
            amount = max(0.0, min(100.0, float(value)))
            fill = RED if amount >= 85 else CYAN if key == "cpu" else BLUE
            bar_width = (width - 4) * amount / 100
            if bar_width > 0:
                canvas.create_rectangle(2, 5, 2 + bar_width, height - 5,
                                        fill=fill, outline="")

    def _refresh_dashboard(self) -> None:
        self._refresh_system()
        self._update_voice_status()
        if hasattr(self, "dashboard_mic"):
            status = "Microphone · listening" if self.listening else "Microphone · idle, not recording"
            self.dashboard_mic.configure(text=status, fg=GREEN if self.listening else MUTED)
            self.dashboard_tts.configure(
                text="Speech engine · ready" if self.voice_output.available else "Speech engine · unavailable",
                fg=GREEN if self.voice_output.available else RED,
            )
            self._refresh_model_status()
        self.root.after(5000, self._refresh_dashboard)

    def _resize_visual_canvases(self, event=None) -> None:
        """Scale visual stages with the window while retaining small-screen limits."""
        if event is not None and event.widget is not self.root:
            return
        available_height = max(600, self.root.winfo_height() - 150)
        chat_height = max(250, min(560, int(available_height * 0.36)))
        canvas = getattr(self, "canvas", None)
        if canvas is not None and canvas.winfo_exists() and int(canvas.cget("height")) != chat_height:
            canvas.configure(height=chat_height)

    def _refresh_model_status(self) -> None:
        status = self.local_model.status()
        self.model_ready = self.local_model.is_trained
        if self.model_ready:
            label = f"Trained · {status['training_steps']} updates"
            color = GREEN
        elif self.local_model.load_error:
            label = "Checkpoint invalid · retrain to replace"
            color = RED
        else:
            label = "Untrained · local commands ready"
            color = MUTED
        if hasattr(self, "dashboard_model_status"):
            self.dashboard_model_status.configure(text=label, fg=color)
            self.dashboard_model_metrics.configure(
                text=f"{status['parameter_count']:,} params · {status['epochs']} epochs · "
                     f"loss {status['training_loss'] if status['training_loss'] is not None else '—'}"
            )
        if hasattr(self, "header_status"):
            self.header_status.configure(
                text="● LOCAL MODEL TRAINED" if self.model_ready else "● LOCAL MODEL UNTRAINED",
                fg=GREEN if self.model_ready else MUTED,
            )
        if hasattr(self, "ai_status"):
            self.ai_status.configure(
                text="● Local model trained" if self.model_ready else "● Local model untrained",
                fg=GREEN if self.model_ready else MUTED,
            )
        if hasattr(self, "model_summary"):
            self.model_summary.configure(
                text=(
                    f"{status['name']}\n{status['architecture']}\n"
                    f"Parameters: {status['parameter_count']:,} · Vocabulary: {status['vocabulary_size']}\n"
                    f"Training steps: {status['training_steps']} · Epochs: {status['epochs']}\n"
                    f"Training loss: {status['training_loss'] if status['training_loss'] is not None else 'unavailable'} · "
                    f"Validation loss: {status['validation_loss'] if status['validation_loss'] is not None else 'unavailable'}\n"
                    f"Dataset: {status['dataset_source']}\n"
                    f"Checkpoint: {status['checkpoint']}"
                    + (f"\nCheckpoint warning: {status['checkpoint_error']}" if status['checkpoint_error'] else "")
                )
            )

    def _new_page(self, name: str, title: str) -> tk.Frame:
        page = tk.Frame(self.center, bg=BG)
        page.pack_propagate(False)
        heading = tk.Frame(page, bg=BG)
        heading.pack(fill="x", pady=(4, 12))
        tk.Frame(heading, bg=CYAN, width=4, height=24).pack(side="left", padx=(0, 10))
        tk.Label(heading, text=title, fg=TEXT, bg=BG, font=("Segoe UI", 15, "bold")).pack(side="left")
        self.pages[name] = page
        return page

    def _build_notes_page(self) -> None:
        page = self._new_page("Notes", "NOTES & REMINDERS")
        toolbar = tk.Frame(page, bg=BG)
        toolbar.pack(fill="x", pady=(0, 8))
        self.note_search = ttk.Entry(toolbar, style="Jarvis.TEntry")
        self.note_search.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.note_search.bind("<KeyRelease>", lambda _event: self._refresh_notes())
        self._button(toolbar, "New note", self._new_note, primary=True).pack(side="left")
        content = tk.Frame(page, bg=BG)
        content.pack(fill="both", expand=True)
        list_panel = tk.Frame(content, bg=PANEL, width=195)
        list_panel.pack(side="left", fill="y", padx=(0, 8))
        list_panel.pack_propagate(False)
        self.notes_list = tk.Listbox(list_panel, bg=PANEL, fg=TEXT, selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 9))
        self.notes_list.pack(fill="both", expand=True, padx=5, pady=5)
        self.notes_list.bind("<<ListboxSelect>>", self._select_note)
        editor = tk.Frame(content, bg=PANEL)
        editor.pack(side="left", fill="both", expand=True)
        self.note_title = ttk.Entry(editor, style="Jarvis.TEntry")
        self.note_title.pack(fill="x", padx=10, pady=(10, 6))
        self.note_body = tk.Text(editor, bg=PANEL_LIGHT, fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word", font=("Segoe UI", 10))
        self.note_body.pack(fill="both", expand=True, padx=10, pady=4)
        self.note_timestamp = tk.Label(editor, text="Not saved", fg=MUTED, bg=PANEL, font=("Segoe UI", 8))
        self.note_timestamp.pack(anchor="w", padx=10, pady=(2, 0))
        actions = tk.Frame(editor, bg=PANEL)
        actions.pack(fill="x", padx=10, pady=(4, 10))
        self._button(actions, "Save note", self._save_note, primary=True).pack(side="left")
        self._button(actions, "Delete note", self._delete_note).pack(side="left", padx=6)
        reminder = tk.LabelFrame(page, text="Reminder (stored locally; app must be open to view it)", bg=PANEL, fg=CYAN, font=("Segoe UI", 8))
        reminder.pack(fill="x", pady=(8, 0))
        self.reminder_title = ttk.Entry(reminder, style="Jarvis.TEntry")
        self.reminder_title.insert(0, "Reminder title")
        self.reminder_title.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        self.reminder_due = ttk.Entry(reminder, style="Jarvis.TEntry", width=22)
        self.reminder_due.insert(0, "YYYY-MM-DD HH:MM")
        self.reminder_due.pack(side="left", padx=6, pady=6)
        self.reminder_details = ttk.Entry(reminder, style="Jarvis.TEntry")
        self.reminder_details.insert(0, "Details (optional)")
        self.reminder_details.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        self._button(reminder, "Save", self._add_reminder, primary=True, compact=True).pack(side="left", padx=6)
        self.reminders_list = tk.Listbox(page, height=4, bg=PANEL, fg=TEXT, selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 8))
        self.reminders_list.pack(fill="x", pady=(6, 0))
        reminder_actions = tk.Frame(page, bg=BG)
        reminder_actions.pack(fill="x", pady=(4, 0))
        self._button(reminder_actions, "Complete / reopen", self._complete_reminder, compact=True).pack(side="left")
        self._button(reminder_actions, "Edit selected", self._edit_reminder, compact=True).pack(side="left", padx=6)
        self._button(reminder_actions, "Delete reminder", self._delete_reminder, compact=True, danger=True).pack(side="left", padx=6)

    def _build_memory_page(self) -> None:
        page = self._new_page("Memory", "MEMORY CORE & KNOWLEDGE")
        tk.Label(
            page,
            text="Local memory and imported TXT/CSV excerpts stay on this PC. "
                 "JARVIS only remembers facts you explicitly save.",
            fg=MUTED, bg=BG, wraplength=680, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        memory_panel = tk.LabelFrame(
            page, text="USER MEMORY · STORED IN LOCAL SQLITE", bg=PANEL, fg=CYAN,
            font=("Segoe UI", 8, "bold"),
        )
        memory_panel.pack(fill="x", pady=(0, 8))
        memory_form = tk.Frame(memory_panel, bg=PANEL)
        memory_form.pack(fill="x", padx=7, pady=(6, 4))
        self.memory_key = ttk.Entry(memory_form, style="Jarvis.TEntry", width=19)
        self.memory_key.insert(0, "Memory name")
        self.memory_key.bind("<FocusIn>", lambda _event: self._clear_memory_placeholder(self.memory_key, "Memory name"))
        self.memory_key.pack(side="left", padx=(0, 5))
        self.memory_value = ttk.Entry(memory_form, style="Jarvis.TEntry")
        self.memory_value.insert(0, "Value to remember")
        self.memory_value.bind("<FocusIn>", lambda _event: self._clear_memory_placeholder(self.memory_value, "Value to remember"))
        self.memory_value.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._button(memory_form, "Save memory", self._save_memory, primary=True, compact=True).pack(side="left")
        memory_actions = tk.Frame(memory_panel, bg=PANEL)
        memory_actions.pack(fill="x", padx=7, pady=(0, 5))
        self.memory_list = tk.Listbox(
            memory_actions, height=3, bg=PANEL_LIGHT, fg=TEXT,
            selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 8),
        )
        self.memory_list.pack(side="left", fill="x", expand=True)
        self._button(memory_actions, "Forget selected", self._forget_memory, compact=True, danger=True).pack(side="left", padx=(6, 0))

        knowledge_panel = tk.LabelFrame(
            page, text="LOCAL KNOWLEDGE · KEYWORD SEARCH WITH SOURCE NAMES", bg=PANEL,
            fg=CYAN, font=("Segoe UI", 8, "bold"),
        )
        knowledge_panel.pack(fill="both", expand=True)
        import_row = tk.Frame(knowledge_panel, bg=PANEL)
        import_row.pack(fill="x", padx=7, pady=(6, 4))
        self._button(import_row, "Import TXT / CSV…", self._import_knowledge, primary=True, compact=True).pack(side="left")
        self.knowledge_status = tk.Label(import_row, text="No files imported", fg=MUTED, bg=PANEL, font=("Segoe UI", 8))
        self.knowledge_status.pack(side="left", padx=8)
        source_row = tk.Frame(knowledge_panel, bg=PANEL)
        source_row.pack(fill="x", padx=7, pady=(0, 4))
        self.knowledge_sources = tk.Listbox(
            source_row, height=3, bg=PANEL_LIGHT, fg=TEXT,
            selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 8),
        )
        self.knowledge_sources.pack(side="left", fill="x", expand=True)
        self._button(source_row, "Remove source", self._forget_knowledge, compact=True, danger=True).pack(side="left", padx=(6, 0))
        search_row = tk.Frame(knowledge_panel, bg=PANEL)
        search_row.pack(fill="x", padx=7, pady=(0, 5))
        self.knowledge_query = ttk.Entry(search_row, style="Jarvis.TEntry")
        self.knowledge_query.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.knowledge_query.bind("<Return>", lambda _event: self._search_knowledge())
        self._button(search_row, "Search", self._search_knowledge, compact=True).pack(side="left")
        self.knowledge_results = tk.Listbox(
            knowledge_panel, height=5, bg=PANEL_LIGHT, fg=TEXT,
            selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 8),
        )
        self.knowledge_results.pack(fill="both", expand=True, padx=7, pady=(0, 4))
        self.knowledge_results.bind("<<ListboxSelect>>", self._show_knowledge_hit)
        self.knowledge_detail = tk.Text(
            knowledge_panel, height=4, wrap="word", bg=PANEL_LIGHT, fg=TEXT,
            relief="flat", padx=7, pady=5, font=("Segoe UI", 8), state="disabled",
        )
        self.knowledge_detail.pack(fill="x", padx=7, pady=(0, 7))

    def _build_model_page(self) -> None:
        page = self._new_page("Model", "MY AI MODEL · TRAINING STUDIO")
        tk.Label(
            page,
            text="From-scratch local neural language model. Version 1 is a small byte-bigram "
                 "embedding + softmax model, not a Transformer or a capable general-purpose LLM. "
                 "Weights start randomly; training uses one CPU example at a time.",
            fg=MUTED, bg=BG, wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 8))
        self.model_summary = tk.Label(
            page, text="Loading checkpoint…", fg=TEXT, bg=PANEL, justify="left",
            anchor="w", wraplength=690, padx=10, pady=9, font=("Segoe UI", 9),
        )
        self.model_summary.pack(fill="x", pady=(0, 8))

        training_panel = tk.LabelFrame(
            page, text="TRAIN FROM YOUR OWN LOCAL TEXT", bg=PANEL, fg=CYAN,
            font=("Segoe UI", 8, "bold"),
        )
        training_panel.pack(fill="x", pady=(0, 8))
        file_row = tk.Frame(training_panel, bg=PANEL)
        file_row.pack(fill="x", padx=8, pady=(7, 5))
        self.training_file_var = tk.StringVar()
        self.training_file_entry = ttk.Entry(
            file_row, textvariable=self.training_file_var, style="Jarvis.TEntry", state="readonly"
        )
        self.training_file_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._button(file_row, "Choose TXT / MD / CSV…", self._choose_training_file, compact=True).pack(side="right")
        config_row = tk.Frame(training_panel, bg=PANEL)
        config_row.pack(fill="x", padx=8, pady=(0, 5))
        tk.Label(config_row, text="Epochs", fg=MUTED, bg=PANEL, font=("Segoe UI", 8)).pack(side="left")
        self.training_epochs = ttk.Entry(config_row, width=5, style="Jarvis.TEntry")
        self.training_epochs.insert(0, "3")
        self.training_epochs.pack(side="left", padx=(5, 14))
        tk.Label(config_row, text="Learning rate", fg=MUTED, bg=PANEL, font=("Segoe UI", 8)).pack(side="left")
        self.training_lr = ttk.Entry(config_row, width=8, style="Jarvis.TEntry")
        self.training_lr.insert(0, "0.01")
        self.training_lr.pack(side="left", padx=5)
        self.training_buttons = tk.Frame(training_panel, bg=PANEL)
        self.training_buttons.pack(fill="x", padx=8, pady=(0, 4))
        self.training_button = self._button(
            self.training_buttons, "Start Training", lambda: self._start_model_training(False),
            compact=True, primary=True,
        )
        self.training_button.pack(side="left")
        self._button(
            self.training_buttons, "Train synthetic demo", lambda: self._start_model_training(True),
            compact=True,
        ).pack(side="left", padx=6)
        self._button(
            self.training_buttons, "Stop safely", self._stop_model_training, compact=True,
        ).pack(side="left")
        tk.Label(
            training_panel,
            text="Synthetic demo is only a pipeline check. Import your own permitted text for meaningful experiments. "
                 "Each corpus is capped at 512 KiB; at most 1,024 training pairs are sampled per epoch.",
            fg=MUTED, bg=PANEL, wraplength=680, justify="left", font=("Segoe UI", 8),
        ).pack(anchor="w", padx=8, pady=(1, 6))
        self.training_status_label = tk.Label(
            training_panel, text="No training run yet.", fg=MUTED, bg=PANEL,
            anchor="w", font=("Segoe UI", 8),
        )
        self.training_status_label.pack(fill="x", padx=8, pady=(0, 7))

        inference_panel = tk.LabelFrame(
            page, text="TEST THE ACTUAL CHECKPOINT", bg=PANEL, fg=CYAN,
            font=("Segoe UI", 8, "bold"),
        )
        inference_panel.pack(fill="both", expand=True)
        prompt_row = tk.Frame(inference_panel, bg=PANEL)
        prompt_row.pack(fill="x", padx=8, pady=7)
        self.generation_input = ttk.Entry(prompt_row, style="Jarvis.TEntry")
        self.generation_input.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.generation_input.bind("<Return>", lambda _event: self._generate_model_sample())
        self._button(prompt_row, "Generate", self._generate_model_sample, compact=True, primary=True).pack(side="right")
        self.generation_output = tk.Text(
            inference_panel, height=6, wrap="word", bg=PANEL_LIGHT, fg=TEXT,
            relief="flat", padx=8, pady=7, font=("Segoe UI", 9), state="disabled",
        )
        self.generation_output.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _choose_training_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose your own language-model training text", parent=self.root,
            filetypes=(("Training text", "*.txt *.md *.csv"), ("All files", "*.*")),
        )
        if path:
            self.training_file_var.set(path)

    def _start_model_training(self, use_demo: bool) -> None:
        if self.model_training:
            return
        try:
            epochs = int(self.training_epochs.get())
            learning_rate = float(self.training_lr.get())
            if not 1 <= epochs <= 100:
                raise ValueError("Epochs must be from 1 to 100.")
            if not 0.00001 <= learning_rate <= 0.1:
                raise ValueError("Learning rate must be between 0.00001 and 0.1.")
        except ValueError as error:
            messagebox.showerror("Training settings", str(error), parent=self.root)
            return
        source = self.training_file_var.get().strip()
        if not use_demo and not source:
            messagebox.showinfo("Training data", "Choose your own TXT, Markdown, or CSV file first.", parent=self.root)
            return
        self.training_stop.clear()
        self.model_training = True
        self.training_button.configure(state="disabled")
        self.training_status_label.configure(
            text="Preparing the local training set…" if not use_demo else "Starting the labelled synthetic demo…",
            fg=BLUE,
        )
        thread = threading.Thread(
            target=self._model_training_worker,
            args=(use_demo, source, epochs, learning_rate),
            daemon=True,
        )
        thread.start()

    def _model_training_worker(
        self, use_demo: bool, source: str, epochs: int, learning_rate: float
    ) -> None:
        try:
            callback = lambda report: self.events.put(("training_progress", report))
            if use_demo:
                result = self.local_model.train_demo(epochs, learning_rate, self.training_stop, callback)
            else:
                result = self.local_model.train_file(source, epochs, learning_rate, self.training_stop, callback)
            self.events.put(("training_complete", result))
        except AIError as error:
            self.events.put(("training_error", str(error)))
        except Exception:
            logging.exception("Unexpected local model training error")
            self.events.put(("training_error", "Local training failed. See the app log for details."))

    def _show_training_progress(self, report: dict[str, object]) -> None:
        validation = report.get("validation_loss")
        val_text = f"{float(validation):.4f}" if validation is not None else "unavailable"
        self.training_status_label.configure(
            text=(
                f"Epoch {report['epoch']} · step total {report['tokens_processed']} · "
                f"train loss {float(report['training_loss']):.4f} · validation loss {val_text} · "
                f"LR {report['learning_rate']} · {report['memory_bytes'] / (1024 * 1024):.2f} MiB model state · "
                f"{report['elapsed_seconds']:.1f}s elapsed"
            ),
            fg=BLUE,
        )

    def _stop_model_training(self) -> None:
        if self.model_training:
            self.training_stop.set()
            self.training_status_label.configure(text="Stop requested; saving at the next safe boundary…", fg=BLUE)

    def _generate_model_sample(self) -> None:
        prompt = self.generation_input.get().strip()
        self.generation_output.configure(state="normal")
        self.generation_output.delete("1.0", "end")
        self.generation_output.insert("1.0", "Generating from the current local checkpoint…")
        self.generation_output.configure(state="disabled")

        def worker() -> None:
            try:
                output = self.local_model.generate(prompt, max_tokens=120)
                self.events.put(("generation_result", output))
            except AIError as error:
                self.events.put(("generation_result", str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_memory_page(self) -> None:
        if not hasattr(self, "memory_list"):
            return
        self.memory_rows = self.memory_core.recall()
        self.memory_list.delete(0, "end")
        for memory in self.memory_rows:
            value = str(memory["value"]).replace("\n", " ")
            if len(value) > 100:
                value = value[:97] + "…"
            self.memory_list.insert("end", f"{memory['key']}: {value}")
        self.knowledge_rows = self.knowledge_base.documents()
        self.knowledge_sources.delete(0, "end")
        for document in self.knowledge_rows:
            self.knowledge_sources.insert(
                "end", f"{document['source']} · {document['chunks']} chunks"
            )
        count = len(self.knowledge_rows)
        self.knowledge_status.configure(
            text=f"{count} local source{'s' if count != 1 else ''} · SQLite"
        )

    def _clear_memory_placeholder(self, entry: ttk.Entry, placeholder: str) -> None:
        if entry.get() == placeholder:
            entry.delete(0, "end")

    def _save_memory(self) -> None:
        try:
            memory_id = self.memory_core.remember(
                self.memory_key.get(), self.memory_value.get()
            )
        except ValueError as error:
            messagebox.showerror("Memory", str(error), parent=self.root)
            return
        self.memory_key.delete(0, "end")
        self.memory_value.delete(0, "end")
        self._refresh_memory_page()
        self.memory_list.selection_clear(0, "end")
        for index, memory in enumerate(self.memory_rows):
            if memory["id"] == memory_id:
                self.memory_list.selection_set(index)
                self.memory_list.see(index)
                break

    def _forget_memory(self) -> None:
        selected = self.memory_list.curselection()
        if not selected:
            return
        memory = self.memory_rows[selected[0]]
        self.memory_core.forget(int(memory["id"]))
        self._refresh_memory_page()

    def _import_knowledge(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import local knowledge", parent=self.root,
            filetypes=(("Text and CSV files", "*.txt *.csv"), ("Text files", "*.txt"), ("CSV files", "*.csv")),
        )
        if not selected:
            return
        try:
            _document_id, chunks, added = self.knowledge_base.import_file(selected)
        except (OSError, ValueError) as error:
            messagebox.showerror("Knowledge import", str(error), parent=self.root)
            return
        self._refresh_memory_page()
        result = f"Imported {chunks} text chunks locally." if added else "This exact file is already in local knowledge."
        messagebox.showinfo("Knowledge import", result, parent=self.root)

    def _forget_knowledge(self) -> None:
        selected = self.knowledge_sources.curselection()
        if not selected:
            return
        document = self.knowledge_rows[selected[0]]
        self.knowledge_base.forget_document(int(document["id"]))
        self.knowledge_results.delete(0, "end")
        self.knowledge_hits = []
        self._refresh_memory_page()

    def _search_knowledge(self) -> list[dict[str, object]]:
        query = self.knowledge_query.get().strip()
        self.knowledge_results.delete(0, "end")
        self.knowledge_hits = self.knowledge_base.search(query)
        if not self.knowledge_hits:
            self.knowledge_results.insert("end", "No matching local passages. Import TXT/CSV files first.")
            self._set_knowledge_detail("")
            return []
        for hit in self.knowledge_hits:
            snippet = " ".join(str(hit["content"]).split())
            if len(snippet) > 95:
                snippet = snippet[:92] + "…"
            self.knowledge_results.insert("end", f"{hit['source']}  ·  {snippet}")
        self.knowledge_results.selection_set(0)
        self._show_knowledge_hit()
        return self.knowledge_hits

    def _set_knowledge_detail(self, text: str) -> None:
        self.knowledge_detail.configure(state="normal")
        self.knowledge_detail.delete("1.0", "end")
        self.knowledge_detail.insert("1.0", text)
        self.knowledge_detail.configure(state="disabled")

    def _show_knowledge_hit(self, _event=None) -> None:
        selected = self.knowledge_results.curselection()
        if not selected or selected[0] >= len(getattr(self, "knowledge_hits", [])):
            return
        hit = self.knowledge_hits[selected[0]]
        self._set_knowledge_detail(
            f"Source: {hit['source']}  |  matched: {', '.join(hit['matched_terms'])}\n\n{hit['content']}"
        )

    def _build_search_page(self) -> None:
        page = self._new_page("Web Search", "WEB SEARCH")
        tk.Label(page, text="Search opens your browser. JARVIS does not claim to verify or summarize live results.", fg=MUTED, bg=BG, wraplength=570, justify="left").pack(anchor="w", pady=(0, 10))
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x")
        self.web_query = ttk.Entry(row, style="Jarvis.TEntry")
        self.web_query.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=4)
        self.web_query.bind("<Return>", lambda _event: self._perform_search())
        self._button(row, "Search Web", self._perform_search, primary=True).pack(side="left")
        tk.Label(page, text="RECENT SEARCHES", fg=MUTED, bg=BG, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(18, 6))
        self.search_list = tk.Listbox(page, bg=PANEL, fg=TEXT, selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 10))
        self.search_list.pack(fill="both", expand=True)
        self.search_list.bind("<Double-Button-1>", self._repeat_search)
        self._button(page, "Search selected again", self._repeat_search, compact=True).pack(anchor="e", pady=6)

    def _build_apps_page(self) -> None:
        page = self._new_page("Applications", "APPLICATIONS")
        tk.Label(page, text="Approved Windows applications and user-selected shortcuts. Shortcuts run only after you add them.", fg=MUTED, bg=BG, wraplength=570, justify="left").pack(anchor="w", pady=(0, 10))
        quick = tk.Frame(page, bg=BG)
        quick.pack(fill="x")
        for name in ("Notepad", "Calculator", "Paint", "Browser"):
            self._button(quick, name, lambda app=name.lower(): self._launch_app(app)).pack(side="left", padx=(0, 6))
        row = tk.Frame(page, bg=BG)
        row.pack(fill="x", pady=(16, 6))
        self._button(row, "Add executable shortcut…", self._add_shortcut, primary=True).pack(side="left")
        self._button(row, "Open selected", self._launch_selected_shortcut).pack(side="left", padx=6)
        self._button(row, "Remove selected", self._remove_shortcut).pack(side="left", padx=6)
        self.shortcuts_list = tk.Listbox(page, bg=PANEL, fg=TEXT, selectbackground="#1c4d80", relief="flat", font=("Segoe UI", 10))
        self.shortcuts_list.pack(fill="both", expand=True)
        self.shortcuts_list.bind("<Double-Button-1>", self._launch_selected_shortcut)

    def _build_system_page(self) -> None:
        page = self._new_page("System Info", "SYSTEM INFORMATION")
        self.system_text = tk.Text(page, wrap="word", bg=PANEL, fg=TEXT, relief="flat", padx=14, pady=14, font=("Segoe UI", 10), state="disabled")
        self.system_text.pack(fill="both", expand=True)
        self._button(page, "Refresh now", self._refresh_system, primary=True).pack(anchor="e", pady=(8, 0))

    def _build_automation_page(self) -> None:
        page = self._new_page("Automation", "AUTOMATION & TOOLS")
        tk.Label(page, text="Supported actions are explicit and user initiated. JARVIS never runs arbitrary AI-generated terminal commands.", fg=MUTED, bg=BG, wraplength=570, justify="left").pack(anchor="w", pady=(0, 10))
        for title, description, callback in (
            ("Open Notepad", "Launch the allow-listed Windows text editor.", lambda: self._launch_app("notepad")),
            ("Open Calculator", "Launch the allow-listed Windows calculator.", lambda: self._launch_app("calculator")),
            ("Open Paint", "Launch Paint when it is installed.", lambda: self._launch_app("paint")),
            ("Open website", "Enter a URL and open it in your default browser.", self._prompt_website),
            ("Create a note", "Save a note locally in the application database.", self._new_note),
            ("Open selected folder", "Choose a folder to open in Windows Explorer.", self._open_folder),
            ("Search files", "Select a directory and list up to 500 file names.", self._start_file_search),
            ("System information", "Show real CPU, memory, disk, battery, and Windows metrics.", lambda: self._show_page("System Info")),
        ):
            card = tk.Frame(page, bg=PANEL, highlightbackground="#1a3652", highlightthickness=1)
            card.pack(fill="x", pady=3)
            text = tk.Frame(card, bg=PANEL)
            text.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            tk.Label(text, text=title, fg=TEXT, bg=PANEL, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            tk.Label(text, text=description, fg=MUTED, bg=PANEL, font=("Segoe UI", 8)).pack(anchor="w")
            self._button(card, "Run", callback, compact=True, primary=True).pack(side="right", padx=8, pady=8)

    def _button(self, parent: tk.Widget, text: str, command, primary: bool = False, compact: bool = False, danger: bool = False) -> tk.Button:
        bg = "#2676db" if primary else PANEL_LIGHT
        fg = "white" if primary else (RED if danger else TEXT)
        hover_bg = "#328be4" if primary else "#173b67"
        button = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=hover_bg, activeforeground="white",
            relief="flat", bd=0, padx=8 if compact else 13,
            pady=5 if compact else 8, cursor="hand2",
            font=("Segoe UI", 8 if compact else 9, "bold"),
            highlightthickness=1,
            highlightbackground="#254570",
            highlightcolor=CYAN,
        )
        button.bind("<Enter>", lambda _event: self._transition_button(button, hover_bg))
        button.bind("<Leave>", lambda _event: self._transition_button(button, bg))
        return button

    def _transition_button(self, button: tk.Button, target_color: str) -> None:
        """Ease button hover color over a few frames for subtle UI feedback."""
        pending = getattr(button, "_jarvis_transition_after", None)
        if pending:
            try:
                button.after_cancel(pending)
            except tk.TclError:
                pass
        try:
            start = button.winfo_rgb(button.cget("bg"))
            end = button.winfo_rgb(target_color)
        except tk.TclError:
            return

        def frame(index: int = 1) -> None:
            ratio = min(index / 5, 1.0)
            channels = [
                round((left + (right - left) * ratio) / 257)
                for left, right in zip(start, end)
            ]
            color = "#" + "".join(f"{channel:02x}" for channel in channels)
            try:
                button.configure(bg=color)
                if index < 5:
                    button._jarvis_transition_after = button.after(18, lambda: frame(index + 1))
                else:
                    button._jarvis_transition_after = None
            except tk.TclError:
                return

        frame()

    def _append_message(self, name: str, content: str, role: str, persist: bool = True) -> None:
        self.chat.configure(state="normal")
        tag = "user" if role == "user" else ("assistant" if role == "assistant" else "system")
        self.chat.insert("end", f"{datetime.now().astimezone().strftime('%H:%M')}  ", "timestamp")
        self.chat.insert("end", f"{name}\n", tag)
        content_tag = f"{role}_body" if role in ("user", "assistant") else "body"
        self.chat.insert("end", content.strip() + "\n\n", content_tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")
        if persist and self._history_enabled():
            try:
                self.storage.add_message(role, content)
            except sqlite3.Error:
                logging.exception("Could not save conversation history")
                messagebox.showwarning(
                    "Conversation not saved",
                    "JARVIS couldn't save this message to local history. It remains visible for this session; check disk space and folder permissions.",
                    parent=self.root,
                )

    def _load_history(self) -> None:
        if not self._history_enabled():
            return
        try:
            self.messages = self.storage.get_messages()
            timestamps = self.storage.message_timestamps()
        except sqlite3.Error:
            logging.exception("Could not load conversation history")
            messagebox.showwarning(
                "History unavailable",
                "JARVIS couldn't read saved conversation history. The current session can still continue.",
                parent=self.root,
            )
            return
        if not self.messages:
            return
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        for index, item in enumerate(self.messages):
            role = item["role"]
            self.chat.configure(state="normal")
            try:
                stamp = datetime.fromisoformat(timestamps[index]).astimezone().strftime("%H:%M")
            except (ValueError, IndexError):
                stamp = ""
            self.chat.insert("end", f"{stamp}  ", "timestamp")
            self.chat.insert("end", f"{'YOU' if role == 'user' else 'JARVIS'}\n", role)
            content_tag = f"{role}_body" if role in ("user", "assistant") else "body"
            self.chat.insert("end", item["content"].strip() + "\n\n", content_tag)
            self.chat.configure(state="disabled")
        self.chat.see("end")

    def _history_enabled(self) -> bool:
        return bool(self.settings.get("save_history", False))

    def _local_reply(self, response: str) -> None:
        self._append_message("JARVIS", response, "assistant")
        self.messages.append({"role": "assistant", "content": response})
        if hasattr(self, "state_label"):
            self.state_label.configure(text="LOCAL MEMORY / KNOWLEDGE", fg=CYAN)

    def _format_knowledge_hits(self, hits: list[dict[str, object]]) -> str:
        sections = ["Local knowledge excerpts, ranked by keyword overlap (not a generated answer):"]
        for index, hit in enumerate(hits, start=1):
            sections.append(f"[{index}] {hit['source']}\n{hit['content']}")
        return "\n\n".join(sections)

    def _send(self) -> None:
        if self.busy:
            return
        text = self.input.get().strip()
        if not text:
            return
        self.ai_error = False
        self.input.delete(0, "end")
        self._append_message("YOU", text, "user")
        self.messages.append({"role": "user", "content": text})

        remember_match = re.fullmatch(
            r"remember\s*:\s*(.{1,80}?)\s*=\s*(.{1,1000})", text, re.IGNORECASE
        )
        if remember_match:
            try:
                self.memory_core.remember(remember_match.group(1), remember_match.group(2))
                self._local_reply(f"Saved local memory: {remember_match.group(1).strip()}.")
                if self.current_page == "Memory":
                    self._refresh_memory_page()
            except ValueError as error:
                self._local_reply(str(error))
            return

        forget_match = re.fullmatch(r"forget\s+memory\s*:\s*(.{1,80})", text, re.IGNORECASE)
        if forget_match:
            matches = self.memory_core.recall(forget_match.group(1).strip())
            exact = next((item for item in matches if str(item["key"]).casefold() == forget_match.group(1).strip().casefold()), None)
            if exact:
                self.memory_core.forget(int(exact["id"]))
                self._local_reply(f"Forgot local memory: {exact['key']}.")
                if self.current_page == "Memory":
                    self._refresh_memory_page()
            else:
                self._local_reply("I couldn't find a saved memory with that exact name.")
            return

        recall_match = re.fullmatch(r"what\s+do\s+you\s+remember(?:\s+about\s+(.+?))?[?.!]*", text, re.IGNORECASE)
        if recall_match:
            memories = self.memory_core.recall((recall_match.group(1) or "").strip())
            if memories:
                response = "Your saved local memories:\n" + "\n".join(
                    f"• {item['key']}: {item['value']}" for item in memories[:20]
                )
            else:
                response = "No saved memories match. Save one with: remember: name = value"
            self._local_reply(response)
            return

        explicit_knowledge = re.fullmatch(
            r"(?:knowledge\s*:\s*|search\s+my\s+knowledge\s+for\s+)(.+)",
            text, re.IGNORECASE,
        )
        if explicit_knowledge:
            query = explicit_knowledge.group(1).strip()
            hits = self.knowledge_base.search(query)
            response = self._format_knowledge_hits(hits) if hits else (
                "No matching local knowledge passages. Import a TXT or CSV file in Memory & Knowledge first."
            )
            self._local_reply(response)
            return

        open_match = re.fullmatch(r"(?:open|show)\s+(?:a\s+)?(file|folder)[?.!]*", text, re.IGNORECASE)
        if open_match:
            selected = (
                filedialog.askopenfilename(title="Choose a file to open", parent=self.root)
                if open_match.group(1).lower() == "file"
                else filedialog.askdirectory(title="Choose a folder to open", parent=self.root)
            )
            if not selected:
                result = "Selection cancelled."
            elif not hasattr(os, "startfile"):
                result = "Opening selected files and folders is supported on Windows only."
            else:
                try:
                    os.startfile(selected)
                    result = f"Opened the selected {'file' if open_match.group(1).lower() == 'file' else 'folder'}."
                except OSError:
                    result = "Windows couldn't open that selection. Check that the file exists and your account has access."
            self._append_message("JARVIS", result, "assistant")
            self.messages.append({"role": "assistant", "content": result})
            return
        if re.fullmatch(r"(?:search|find)\s+(?:for\s+)?files?[?.!]*", text, re.IGNORECASE):
            folder = filedialog.askdirectory(title="Choose a folder to search", parent=self.root)
            if not folder:
                self._append_message("JARVIS", "File search cancelled.", "assistant")
                return
            self._set_busy(True, "SEARCHING FILES")
            threading.Thread(target=self._file_search_worker, args=(folder,), daemon=True).start()
            return
        if re.fullmatch(r"(?:show|get|check)\s+(?:my\s+)?system\s+(?:and\s+)?network\s+status[?.!]*", text, re.IGNORECASE):
            self._set_busy(True, "READING SYSTEM STATUS")
            threading.Thread(target=self._local_system_worker, daemon=True).start()
            return
        local_result = run_command(text)
        if local_result is not None:
            self._local_reply(local_result)
            return
        try:
            knowledge_hits = self.knowledge_base.search(text)
        except Exception:
            logging.exception("Local knowledge search failed")
            knowledge_hits = []
        if knowledge_hits:
            self._local_reply(self._format_knowledge_hits(knowledge_hits))
            return
        if self.model_training:
            self._local_reply("The local model is training. Its weights are locked until the current epoch checkpoint is saved.")
            return
        client = self.local_model
        self._set_busy(True, "THINKING")
        history = self.messages[-40:].copy()
        threading.Thread(target=self._chat_worker, args=(client, history), daemon=True).start()

    def _file_search_worker(self, folder: str) -> None:
        try:
            result = run_command("search files", choose_directory=lambda: folder)
            self.events.put(("local", result or "File search did not return a result."))
        except Exception:
            logging.exception("Unexpected file search failure")
            self.events.put(("local", "File search failed. Check folder permissions and try again."))

    def _local_system_worker(self) -> None:
        try:
            result = run_command("show system and network status")
            self.events.put(("local", result or "System information is unavailable."))
        except Exception:
            logging.exception("Could not read system information")
            self.events.put(("local", "System information is currently unavailable."))

    def _chat_worker(self, client: LocalLanguageModel, history: list[dict[str, str]]) -> None:
        response: list[str] = []
        try:
            for chunk in client.chat_stream(history):
                response.append(chunk)
                self.events.put(("stream_chunk", chunk))
            self.events.put(("stream_complete", "".join(response)))
        except AIError as error:
            self.events.put(("error", str(error)))
        except Exception:
            logging.exception("Unexpected local language model failure")
            self.events.put(("error", "The local JARVIS model could not generate a response. Check its training state and checkpoint."))

    def _toggle_listening(self) -> None:
        if self.listening:
            self.listening = False
            if self.listen_cancel is not None:
                self.listen_cancel.set()
            self.mic_button.configure(text="…", state="disabled")
            self.voice_dial_label.configure(text="STOPPING")
            self.mic_status.configure(text="● Stopping microphone…", fg=BLUE)
            self.state_label.configure(text="STOPPING LISTENING", fg=BLUE)
            return
        if self.busy:
            return
        self.listening = True
        self.listen_cancel = threading.Event()
        self.mic_button.configure(text="■")
        self.voice_dial_label.configure(text="LISTENING", fg=GREEN)
        self.mic_status.configure(text="● Listening…", fg=GREEN)
        self.state_label.configure(text="LISTENING — speak now", fg=GREEN)
        threading.Thread(target=self._listen_worker, args=(self.listen_cancel,), daemon=True).start()

    def _listen_worker(self, cancelled: threading.Event) -> None:
        try:
            text = self.voice_input.listen(cancelled)
            self.events.put(("voice_cancelled", None) if cancelled.is_set() else ("recognized", text))
        except RuntimeError as error:
            if cancelled.is_set():
                self.events.put(("voice_cancelled", None))
            else:
                self.events.put(("voice_error", str(error)))
        except Exception:
            logging.exception("Unexpected microphone failure")
            if cancelled.is_set():
                self.events.put(("voice_cancelled", None))
            else:
                self.events.put(("voice_error", "Microphone recognition failed. Check the device and Windows privacy permissions."))

    def _stop_speaking(self) -> None:
        self.voice_output.stop()
        self.speaking = False
        self.state_label.configure(text="SYSTEM READY", fg=CYAN)

    def _poll_events(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "stream_chunk":
                    self._append_stream_chunk(str(value))
                elif event == "stream_complete":
                    response = str(value)
                    if response:
                        self.ai_error = False
                    if self.stream_in_progress:
                        self.chat.configure(state="normal")
                        self.chat.insert("end", "\n\n")
                        self.chat.configure(state="disabled")
                        self.stream_in_progress = False
                    if not response:
                        self._append_message("JARVIS", "The local model returned an empty response.", "system")
                    else:
                        self.messages.append({"role": "assistant", "content": response})
                        if self._history_enabled():
                            try:
                                self.storage.add_message("assistant", response)
                            except sqlite3.Error:
                                logging.exception("Could not save streamed conversation response")
                        self._set_busy(False, "SPEAKING")
                        self.speaking = self.voice_output.available
                        self.ai_status.configure(text="● Local model generated output", fg=GREEN)
                        self._refresh_model_status()
                        self.header_status.configure(text="● LOCAL OUTPUT RECEIVED", fg=GREEN)
                        self.voice_output.speak(response)
                    if not response:
                        self._set_busy(False, "SYSTEM READY")
                elif event == "chat":
                    response = str(value)
                    self.ai_error = False
                    self._append_message("JARVIS", response, "assistant")
                    self.messages.append({"role": "assistant", "content": response})
                    self._set_busy(False, "SPEAKING")
                    self.speaking = self.voice_output.available
                    self.ai_status.configure(text="● Local model generated output", fg=GREEN)
                    self._refresh_model_status()
                    self.voice_output.speak(response)
                elif event == "error":
                    self.ai_error = True
                    if self.stream_in_progress:
                        self.chat.configure(state="normal")
                        self.chat.insert("end", "\n\n")
                        self.chat.configure(state="disabled")
                        self.stream_in_progress = False
                    self._append_message("JARVIS", str(value), "assistant")
                    self._set_busy(False, "SYSTEM READY")
                    self.ai_status.configure(text="● Local model error", fg=RED)
                    self.dashboard_model_status.configure(text="Local inference failed", fg=RED)
                    self.header_status.configure(text="● LOCAL MODEL ERROR", fg=RED)
                elif event == "local":
                    self._append_message("JARVIS", str(value), "assistant")
                    self.messages.append({"role": "assistant", "content": str(value)})
                    self._set_busy(False, "SYSTEM READY")
                elif event == "system":
                    self._render_system(value)
                elif event == "system_voice":
                    if self.system_snapshot is not None:
                        self.system_text.configure(state="normal")
                        self.system_text.insert(
                            "end",
                            f"\n\nMICROPHONE\n{value}"
                            f"\n\nSPEECH SYNTHESIS\n"
                            f"{'Available' if self.voice_output.available else 'Unavailable'}"
                            f"\n\nLOCAL MODEL\n{self.local_model.status()['name']}\n"
                            f"Training steps: {self.local_model.status()['training_steps']}",
                        )
                        self.system_text.configure(state="disabled")
                elif event == "system_error":
                    self.system_refresh_pending = False
                    self.dashboard_os.configure(text="Unavailable")
                    self.dashboard_processor.configure(text="Unavailable")
                    self.dashboard_cpu.configure(text="Unavailable")
                    self.dashboard_memory.configure(text="Unavailable")
                    self.dashboard_disk.configure(text="Unavailable")
                    self.dashboard_battery.configure(text="Unavailable")
                    self.system_text.configure(state="normal")
                    self.system_text.delete("1.0", "end")
                    self.system_text.insert("1.0", str(value))
                    self.system_text.configure(state="disabled")
                elif event == "training_progress":
                    self._show_training_progress(value)
                elif event == "training_complete":
                    self.model_training = False
                    self.model_ready = self.local_model.is_trained
                    self.training_button.configure(state="normal")
                    self.training_status_label.configure(
                        text="Training stopped and checkpoint saved." if value.get("stopped")
                        else "Training complete; checkpoint saved.", fg=GREEN,
                    )
                    self._refresh_model_status()
                elif event == "training_error":
                    self.model_training = False
                    self.training_button.configure(state="normal")
                    self.training_status_label.configure(text=str(value), fg=RED)
                    self._refresh_model_status()
                elif event == "generation_result":
                    self.generation_output.configure(state="normal")
                    self.generation_output.delete("1.0", "end")
                    self.generation_output.insert("1.0", str(value))
                    self.generation_output.configure(state="disabled")
                elif event == "spoken":
                    self.speaking = False
                    if not self.busy and not self.listening:
                        self.state_label.configure(text="SYSTEM READY", fg=CYAN)
                elif event == "recognized":
                    if not self.listening:
                        continue
                    self.listening = False
                    self.mic_button.configure(text="🎙")
                    self.mic_button.configure(state="normal")
                    self.voice_dial_label.configure(text="MIC OFF", fg=MUTED)
                    self.mic_status.configure(text="● Mic idle", fg=MUTED)
                    self.input.insert(0, str(value))
                    self._send()
                elif event == "voice_cancelled":
                    self.mic_button.configure(text="🎙", state="normal")
                    self.voice_dial_label.configure(text="MIC OFF", fg=MUTED)
                    self.mic_status.configure(text="● Mic idle", fg=MUTED)
                    self.state_label.configure(text="SYSTEM READY", fg=CYAN)
                elif event == "voice_error":
                    self.listening = False
                    self.mic_button.configure(text="🎙", state="normal")
                    self.voice_dial_label.configure(text="MIC OFF", fg=MUTED)
                    self.mic_status.configure(text="● Mic unavailable", fg=RED)
                    self._append_message("JARVIS", str(value), "system")
                    self.state_label.configure(text="SYSTEM READY", fg=CYAN)
        except queue.Empty:
            pass
        self._update_voice_status()
        self.root.after(100, self._poll_events)

    def _append_stream_chunk(self, chunk: str) -> None:
        if self.typing_visible:
            self.chat.configure(state="normal")
            start = self.chat.search("JARVIS · working…", "1.0", "end")
            if start:
                self.chat.delete(start, f"{start} lineend + 1 chars")
            self.chat.insert("end", f"{datetime.now().astimezone().strftime('%H:%M')}  ", "timestamp")
            self.chat.insert("end", "JARVIS\n", "assistant")
            self.typing_visible = False
            self.stream_in_progress = True
        self.chat.insert("end", chunk, "assistant_body")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _set_busy(self, busy: bool, state: str) -> None:
        self.busy = busy
        self.send_button.configure(state="disabled" if busy else "normal")
        self.mic_button.configure(state="disabled" if busy else "normal")
        self.state_label.configure(text=state, fg=BLUE if busy else CYAN)
        if busy and not self.typing_visible:
            self.chat.configure(state="normal")
            self.chat.insert("end", "JARVIS · working…\n\n", "system")
            self.chat.configure(state="disabled")
            self.chat.see("end")
            self.typing_visible = True
        elif not busy and self.typing_visible:
            self.chat.configure(state="normal")
            start = self.chat.search("JARVIS · working…", "1.0", "end")
            if start:
                self.chat.delete(start, f"{start} lineend + 1 chars")
            self.chat.configure(state="disabled")
            self.typing_visible = False

    def _update_voice_status(self) -> None:
        if self.voice_output.available:
            self.tts_status.configure(text="● Speech engine ready", fg=GREEN)
        elif self.voice_output.error:
            self.tts_status.configure(text="● Speech unavailable", fg=RED)

    def _animate(self) -> None:
        if self.animation_enabled:
            self.animation_phase = (self.animation_phase + 1) % 360
        mode = (
            "LISTENING" if self.listening else
            "THINKING" if self.busy else
            "SPEAKING" if self.speaking else
            "ERROR" if self.ai_error else
            "OFFLINE" if not self.model_ready else "READY"
        )
        state_text = {
            "LISTENING": "LISTENING — SPEAK NOW",
            "THINKING": "AI PROCESSING",
            "SPEAKING": "JARVIS SPEAKING",
            "ERROR": "LOCAL MODEL ERROR",
            "OFFLINE": "MODEL UNTRAINED · LOCAL TOOLS READY",
            "READY": "SYSTEM READY",
        }[mode]
        if hasattr(self, "state_label") and self.state_label.cget("text") != state_text:
            state_color = RED if mode == "ERROR" else MUTED if mode == "OFFLINE" else GREEN if mode == "LISTENING" else BLUE if mode in ("THINKING", "SPEAKING") else CYAN
            self.state_label.configure(text=state_text, fg=state_color)
        cpu_load = (
            self.system_snapshot.cpu_percent
            if self.system_snapshot is not None
            else None
        )
        phase = self.animation_phase if self.animation_enabled else 0
        if self.current_page in ("AI Chat", "Voice Control", "Home"):
            visual_canvas = self.canvas
            is_home = self.current_page == "Home"
            visual_height = max(visual_canvas.winfo_height(), 120)
            draw_hud(
                visual_canvas, phase=phase,
                center_y=visual_height * (0.43 if is_home else 0.42),
                core_radius=min(118, max(58, visual_height * (0.21 if is_home else 0.25))),
                mode=mode, logo=None, cpu_load=cpu_load,
                cpu_history=tuple(self.cpu_history), animated=self.animation_enabled,
                hero=True, details=is_home, quality=self.graphics_quality,
            )
        interval = {"Low": 250, "Balanced": 120, "High": 50}.get(self.graphics_quality, 50)
        self.root.after(interval if self.animation_enabled else 500, self._animate)

    def _open_settings(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("JARVIS Settings")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x640")
        panel = tk.Frame(dialog, bg=PANEL)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(panel, text="LOCAL AI & PRIVACY SETTINGS", bg=PANEL, fg=CYAN, font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(16, 8))
        tk.Label(
            panel,
            text="JARVIS uses its own local checkpoint. No external model or hosted inference is configured.",
            bg=PANEL, fg=MUTED, wraplength=490, justify="left", font=("Segoe UI", 9),
        ).pack(anchor="w", padx=18, pady=(0, 12))
        model_button = self._button(
            panel, "Open My AI Model & Training", lambda: (dialog.destroy(), self._show_page("Model")),
            primary=True,
        )
        model_button.pack(fill="x", padx=18, pady=(0, 12))
        self._setting_label(panel, "Voice language")
        language_values = ("en-IN — English / Hinglish", "hi-IN — Hindi")
        saved_language = str(self.settings.get("voice_language", "en-IN"))
        language_var = tk.StringVar(
            value=language_values[1] if saved_language == "hi-IN" else language_values[0]
        )
        ttk.Combobox(
            panel, textvariable=language_var, values=language_values, state="readonly"
        ).pack(fill="x", padx=18, pady=(0, 8))
        self._setting_label(panel, "Listening timeout in seconds (3–60)")
        timeout_var = tk.StringVar(value=str(self.settings.get("listening_timeout", 8)))
        ttk.Entry(panel, textvariable=timeout_var, style="Jarvis.TEntry").pack(fill="x", padx=18, pady=(0, 8))
        history_var = tk.BooleanVar(value=self._history_enabled())
        ttk.Checkbutton(panel, text="Save conversation history on this PC", variable=history_var, style="Jarvis.TCheckbutton").pack(anchor="w", padx=18, pady=(0, 4))
        animation_var = tk.BooleanVar(value=self.animation_enabled)
        ttk.Checkbutton(panel, text="Enable animated visualizer", variable=animation_var, style="Jarvis.TCheckbutton").pack(anchor="w", padx=18, pady=(0, 4))
        self._setting_label(panel, "Graphics quality · controls HUD detail and refresh rate")
        quality_var = tk.StringVar(value=self.graphics_quality if self.graphics_quality in ("Low", "Balanced", "High") else "High")
        ttk.Combobox(
            panel, textvariable=quality_var, values=("Low", "Balanced", "High"),
            state="readonly",
        ).pack(fill="x", padx=18, pady=(0, 8))
        self._setting_label(panel, "Startup page")
        startup_page_var = tk.StringVar(value=str(self.settings.get("startup_page", "Home")))
        ttk.Combobox(
            panel, textvariable=startup_page_var, values=("AI Chat", "Home"),
            state="readonly",
        ).pack(fill="x", padx=18, pady=(0, 8))
        buttons = tk.Frame(panel, bg=PANEL)
        buttons.pack(fill="x", padx=18, pady=(12, 14))

        def form_settings() -> dict[str, object]:
            try:
                listening_timeout = int(timeout_var.get())
                if not 3 <= listening_timeout <= 60:
                    raise ValueError
            except ValueError:
                raise ValueError("Listening timeout must be a whole number from 3 to 60 seconds.") from None
            return {
                "save_history": history_var.get(),
                "animations": animation_var.get(),
                "graphics_quality": quality_var.get(),
                "startup_page": startup_page_var.get(),
                "voice_language": "hi-IN" if language_var.get().startswith("hi-IN") else "en-IN",
                "listening_timeout": listening_timeout,
            }

        def save_settings() -> None:
            try:
                values = form_settings()
                self.settings.update(values)
                self.storage.save_settings(values)
                self.animation_enabled = bool(values["animations"])
                self.graphics_quality = str(values["graphics_quality"])
                self.voice_input.language = str(values["voice_language"])
                self.voice_input.timeout = int(values["listening_timeout"])
                if not history_var.get():
                    self.storage.clear_messages()
                    self.messages.clear()
                    self.chat.configure(state="normal")
                    self.chat.delete("1.0", "end")
                    self.chat.configure(state="disabled")
                    self._append_message("JARVIS", "History saving is off; previous local messages were deleted.", "assistant", persist=False)
                elif history_var.get():
                    self.storage.clear_messages()
                    for item in self.messages[-40:]:
                        self.storage.add_message(item["role"], item["content"])
                self._refresh_model_status()
                dialog.destroy()
            except (OSError, sqlite3.Error):
                logging.exception("Could not save JARVIS settings")
                messagebox.showerror(
                    "Settings could not be saved",
                    "JARVIS couldn't write settings to your local profile. Check disk space and folder permissions.",
                    parent=dialog,
                )
            except ValueError as error:
                messagebox.showerror("Settings", str(error), parent=dialog)

        self._button(buttons, "Clear settings & data", lambda: self._delete_data(dialog)).pack(side="left")
        self._button(buttons, "Save settings", save_settings, primary=True).pack(side="right")
        self.events.put(("settings_bind", dialog))
        dialog.wait_window()

    def _setting_label(self, parent: tk.Widget, text: str) -> None:
        tk.Label(parent, text=text, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(2, 4))

    def _show_help(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("JARVIS Help")
        dialog.configure(bg=BG)
        dialog.geometry("620x520")
        dialog.minsize(500, 400)
        dialog.transient(self.root)
        tk.Label(
            dialog,
            text="JARVIS QUICK HELP",
            bg=BG,
            fg=CYAN,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 10))
        help_text = tk.Text(
            dialog, wrap="word", bg=PANEL, fg=TEXT, relief="flat",
            padx=16, pady=14, font=("Segoe UI", 10), state="normal",
        )
        help_text.pack(fill="both", expand=True, padx=22, pady=(0, 14))
        help_text.insert(
            "1.0",
            "Getting started\n"
            "Open My AI Model to train the randomly initialized local byte-bigram model "
            "on an approved TXT, Markdown, or CSV file. Its tiny architecture is experimental "
            "and is not a general-purpose assistant.\n\n"
            "Chat and voice\n"
            "Type a message and press Enter or Send. Speak activates the microphone only "
            "when clicked; offline speech recognition is not implemented yet, and audio "
            "is never sent to an online transcription service. "
            "Stop speaking interrupts text-to-speech.\n\n"
            "Local actions\n"
            "Try “open Notepad”, “open Calculator”, “open example.com”, “search the web "
            "for …”, “create note: …”, “show system and network status”, “search files”, "
            "or “open a file”. File/folder selection uses a native picker. JARVIS does not "
            "run terminal commands or destructive actions.\n\n"
            "Privacy and data\n"
            "No external AI API or hosted model is used. Conversation history is off unless "
            "enabled in Settings. Clear chat removes saved conversation history; Delete "
            "stored data removes local settings, history, notes, memories, and knowledge.\n\n"
            "Troubleshooting\n"
            "If model output is poor, the experimental model needs more suitable training text. "
            "If the microphone or speech engine is unavailable, check Windows privacy and "
            "sound settings; text chat remains usable.\n\n"
            "Design reference\nThe supplied JARVIS image is optional inspiration only; "
            "the working controls are drawn by the app.",
        )
        help_text.configure(state="disabled")
        self._button(
            dialog, "View design reference", self._show_reference_image, compact=True
        ).pack(anchor="w", padx=22, pady=(0, 8))
        self._button(dialog, "Close", dialog.destroy, primary=True).pack(anchor="e", padx=22, pady=(0, 18))
        dialog.focus_set()

    def _show_about(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("About JARVIS")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.geometry("420x500")
        if self.logo_about is not None:
            tk.Label(dialog, image=self.logo_about, bg=BG).pack(pady=(12, 0))
        else:
            tk.Label(dialog, text="◈", fg=CYAN, bg=BG, font=("Segoe UI", 42, "bold")).pack(pady=(18, 0))
        tk.Label(dialog, text="J.A.R.V.I.S. AI", fg=TEXT, bg=BG, font=("Segoe UI", 19, "bold")).pack()
        tk.Label(dialog, text="Version 1.0.0 · Windows desktop assistant", fg=MUTED, bg=BG, font=("Segoe UI", 9)).pack(pady=(4, 12))
        tk.Label(
            dialog,
            text="JARVIS uses an experimental locally trained model. No hosted AI API is connected; "
            "offline speech recognition is not implemented.",
            fg=TEXT,
            bg=BG,
            wraplength=350,
            justify="center",
            font=("Segoe UI", 9),
        ).pack(padx=24, pady=4)
        self._button(dialog, "Close", dialog.destroy, primary=True).pack(pady=18)
        dialog.focus_set()

    def _delete_data(self, parent: tk.Toplevel) -> None:
        if not messagebox.askyesno(
            "Delete stored data",
            "Delete saved settings, conversation history, notes, reminders, saved memories, and all imported knowledge? "
            "This cannot be undone.",
            parent=parent,
        ):
            return
        try:
            self.storage.delete_all()
        except sqlite3.Error:
            logging.exception("Could not delete local JARVIS data")
            messagebox.showerror(
                "Stored data could not be deleted",
                "JARVIS couldn't remove local settings or saved data. Check folder permissions and try again.",
                parent=parent,
            )
            return
        self.settings = {}
        self.messages.clear()
        self.voice_input.language = "en-IN"
        self.voice_input.timeout = 8
        notes_dir = APP_DIR / "notes"
        if notes_dir.exists():
            try:
                shutil.rmtree(notes_dir)
            except OSError:
                messagebox.showerror(
                    "Could not delete all stored data",
                    f"Settings and conversation history were deleted, but local notes could not be removed from:\n{notes_dir}",
                    parent=parent,
                )
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._append_message("JARVIS", "Local settings, memories, knowledge, and conversation data were deleted.", "assistant", persist=False)
        self._refresh_model_status()
        parent.destroy()

    def _clear_chat(self) -> None:
        if not messagebox.askyesno("Clear chat", "Clear the conversation and delete its saved local history?"):
            return
        try:
            self.storage.clear_messages()
        except sqlite3.Error:
            logging.exception("Could not clear conversation history")
            messagebox.showerror(
                "Chat could not be cleared",
                "JARVIS couldn't remove saved conversation history. Check local folder permissions and try again.",
                parent=self.root,
            )
            return
        self.messages.clear()
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._append_message("JARVIS", "Conversation cleared. What would you like to do?", "assistant", persist=False)

    def _close(self) -> None:
        self.voice_output.stop()
        self.root.destroy()


def main() -> None:
    try:
        if not DASHBOARD_HTML_PATH.is_file():
            raise FileNotFoundError(f"Dashboard UI was not packaged: {DASHBOARD_HTML_PATH}")
        import webbrowser

        if not webbrowser.open(DASHBOARD_HTML_PATH.resolve().as_uri(), new=2):
            raise RuntimeError("Windows could not open the dashboard in the default browser.")
    except Exception:
        logging.exception("Application startup failure")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "JARVIS could not start",
            f"The dashboard could not be opened. Diagnostic details are in:\n{LOG_PATH}",
        )
        root.destroy()


if __name__ == "__main__":
    main()
