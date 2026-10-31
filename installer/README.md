# Windows MSI installer

`fixing.msi` is a per-user Windows Installer package built from the PyInstaller
onedir application. It installs under `%LOCALAPPDATA%\Programs\JARVIS` and adds
a JARVIS shortcut to the current user's Start Menu. It does not install a
service or include user data, settings, or logs.

## Build

From the project root in PowerShell, with the project `.venv` set up:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name JARVIS-AI --distpath dist\fixing-release --workpath dist\fixing-work --icon assets\jarvis.ico --add-data "assets;assets" --add-data "dashboard.html;." --add-data "dashboard.css;." --add-data "dashboard.js;." --hidden-import pyttsx3.drivers.sapi5 main.py
.\.venv\Scripts\python.exe installer\build_msi.py --app-dir dist\fixing-release\JARVIS-AI --output fixing.msi
```

`build_msi.py` uses Python 3.11's Windows `msilib` module and embeds the app
files in the MSI cabinet. Rebuild the PyInstaller folder first whenever the
application source or assets change. Python 3.13 removed `msilib`; use the
project's supported Python 3.11 environment to produce this installer.

To install for the current user, double-click `fixing.msi` or run:

```powershell
msiexec /i .\fixing.msi
```

The app can be removed from Windows **Installed apps**. Do not distribute the
unsigned installer without reviewing its contents and signing workflow.
