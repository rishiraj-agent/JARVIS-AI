# JARVIS assets

This folder contains the visual resources used by the desktop app and the
companion browser-style theme.

| Path | Purpose |
| --- | --- |
| `jarvis.ico` | Windows application and executable icon |
| `icons/jarvis-logo.png` | Brand image used by the Tkinter window |
| `icons/jarvis-emblem.svg`, `icons/jarvis-wordmark.svg` | Scalable browser-theme logo variants |
| `themes/jarvis-ui.css` | Responsive visual theme for browser mockups or future web UI |
| `fonts/font-stack.css` | Licensed system-font fallback stack; no font binaries are redistributed |
| `animations/jarvis-orbit.svg` | Animated orbital illustration for browser mockups |
| `sounds/*.wav` | Original optional UI sound effects; not auto-played |
| `ui_gui_images/reference_ui.png` | Optional screenshot shown from Help |
| `ui_gui_images/background/jarvis-grid.svg` | Subtle background texture for the CSS theme |
| `ui_gui_images/avatars/jarvis-assistant.svg` | Assistant avatar for browser-based chat mockups |
| `ui_gui_images/panels/cyan-panel.svg` | Reusable panel-frame artwork for browser mockups |
| `ui_gui_images/illustrations/assistant-orbit.svg` | Static JARVIS orbital illustration |

The current application is native Tkinter. It loads the PNG logo and ICO
directly; it does not load CSS or SVG files or play the sound effects. SVG
resources are used by the CSS theme and can be previewed in a modern browser.

The app uses Windows Segoe UI and Windows speech voices through its existing
voice-output feature. See `sounds/README.md` before opting into sound playback.
Do not put API keys, databases, notes, or private user data here.
