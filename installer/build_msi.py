"""Build a per-user JARVIS Windows Installer package from a PyInstaller folder."""

from __future__ import annotations

import argparse
from pathlib import Path

import msilib
from msilib import schema, sequence


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_CODE = "{B12AE9B8-14FA-4E1B-9218-5F5200B49A46}"
UPGRADE_CODE = "{A80D5476-01D7-4F7C-A095-4DA1A0459FCE}"
PRODUCT_VERSION = "1.0.0"


def add_values(database, table: str, values: list[tuple]) -> None:
    msilib.add_data(database, table, values)


def build_msi(app_dir: Path, output: Path) -> None:
    app_dir = app_dir.resolve()
    executable = app_dir / "JARVIS-AI.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller app executable not found: {executable}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    output.unlink(missing_ok=True)

    database = msilib.init_database(
        str(output),
        schema,
        "JARVIS AI",
        PRODUCT_CODE,
        PRODUCT_VERSION,
        "JARVIS",
    )
    cabinet = msilib.CAB("jarvis.cab")

    # TARGETDIR is the volume root; the app is installed under the current
    # user's LocalAppData\Programs\JARVIS directory.
    target = msilib.Directory(database, cabinet, None, str(app_dir), "TARGETDIR", "SourceDir")
    local = msilib.Directory(database, cabinet, target, "LocalAppDataFolder", "LocalAppDataFolder", ".")
    programs = msilib.Directory(database, cabinet, local, "Programs", "ProgramsFolder", "Programs")
    install_dir = msilib.Directory(database, cabinet, programs, "JARVIS", "INSTALLDIR", "JARVIS")
    install_dir.absolute = str(app_dir)

    feature = msilib.Feature(
        database,
        "MainFeature",
        "JARVIS AI",
        "JARVIS desktop assistant",
        1,
        directory="INSTALLDIR",
    )
    feature.set_current()

    # Give the executable its own key path so Windows Installer can repair the
    # app and keep the Start Menu shortcut tied to the executable component.
    install_dir.start_component("JarvisMain", feature, 0, keyfile="JARVIS-AI.exe")
    exe_file_id = install_dir.add_file("JARVIS-AI.exe")

    directory_map = {app_dir: install_dir}
    for source_dir in sorted((path for path in app_dir.rglob("*") if path.is_dir()), key=lambda p: (len(p.parts), str(p).casefold())):
        relative = source_dir.relative_to(app_dir)
        parent = directory_map[source_dir.parent]
        logical = "DIR_" + str(relative).replace("\\", "_").replace("/", "_").replace("-", "_").replace(".", "_")
        target_name = relative.name
        child = msilib.Directory(database, cabinet, parent, target_name, logical, target_name)
        child.absolute = str(source_dir)
        directory_map[source_dir] = child

    for source_file in sorted((path for path in app_dir.rglob("*") if path.is_file()), key=lambda p: str(p).casefold()):
        if source_file == executable:
            continue
        directory_map[source_file.parent].add_file(source_file.name)

    menu = msilib.Directory(database, cabinet, target, "ProgramMenuFolder", "ProgramMenuFolder", ".")
    menu.absolute = str(app_dir)
    menu_dir = msilib.Directory(database, cabinet, menu, "JARVIS", "JARVISMENUDIR", "JARVIS")
    menu_dir.absolute = str(app_dir)
    add_values(
        database,
        "Shortcut",
        [("JarvisStartMenuShortcut", "JARVISMENUDIR", "JARVIS AI", "JarvisMain", f"[#{exe_file_id}]", None,
          "Launch JARVIS AI", None, None, None, 1, "INSTALLDIR")],
    )
    add_values(database, "RemoveFile", [("RemoveJarvisMenu", "JarvisMain", "*", "JARVISMENUDIR", 2)])

    add_values(
        database,
        "Property",
        [
            ("UpgradeCode", UPGRADE_CODE),
            ("ARPCOMMENTS", "Per-user installation of the JARVIS AI desktop assistant."),
            ("LIMITUI", "1"),
        ],
    )
    execute_sequence = [
        row for row in sequence.InstallExecuteSequence
        if row[0] in {
            "CostInitialize", "FileCost", "CostFinalize", "InstallValidate",
            "InstallInitialize", "ProcessComponents", "CreateFolders", "InstallFiles",
            "CreateShortcuts", "RegisterProduct", "PublishFeatures", "PublishProduct",
            "RemoveShortcuts", "RemoveFiles", "RemoveFolders", "UnpublishFeatures",
            "InstallFinalize",
        }
    ]
    ui_sequence = [
        ("CostInitialize", None, 800),
        ("FileCost", None, 900),
        ("CostFinalize", None, 1000),
        ("ExecuteAction", None, 1300),
    ]
    add_values(database, "InstallExecuteSequence", execute_sequence)
    add_values(database, "InstallUISequence", ui_sequence)

    cabinet.commit(database)
    summary = database.GetSummaryInformation(20)
    summary.SetProperty(msilib.PID_REVNUMBER, msilib.gen_uuid())
    summary.SetProperty(msilib.PID_WORDCOUNT, 2)
    summary.SetProperty(msilib.PID_PAGECOUNT, 200)
    summary.SetProperty(msilib.PID_APPNAME, "JARVIS MSI Builder")
    summary.Persist()
    database.Commit()
    database.Close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, required=True, help="PyInstaller onedir output directory")
    parser.add_argument("--output", type=Path, default=ROOT / "fixing.msi", help="Destination MSI file")
    args = parser.parse_args()
    build_msi(args.app_dir, args.output)
    print(f"Created per-user installer: {args.output.resolve()}")


if __name__ == "__main__":
    main()
