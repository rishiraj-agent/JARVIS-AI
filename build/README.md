# Windows build folder

This directory is reserved for local packaging work. Do not put source assets,
application settings, API keys, or user data here.

## Produce a release

From the project root on Windows with Python 3.11 installed:

```powershell
.\build_exe.bat
```

The script validates the app and tests, stages the complete `assets` folder in
a temporary directory outside the synchronized project, and builds both
variants into a new `dist\release-<build-id>` folder:

- `JARVIS-AI\JARVIS-AI.exe` — portable onedir build; keep the adjacent folder
  contents together.
- `JARVIS-AI.exe` — optional one-file build.

Use `build_exe_onedir.bat` or `build_exe_onefile.bat` for a single variant.
Generated release files belong in `dist`, not in this source-controlled build
instructions folder. Temporary PyInstaller work files are intentionally kept
outside the project directory.
