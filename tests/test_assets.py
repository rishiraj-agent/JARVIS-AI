from __future__ import annotations

import json
import re
import unittest
import wave
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


class AssetPackTests(unittest.TestCase):
    def test_build_manifest_paths_exist(self) -> None:
        manifest = json.loads((ROOT / "build" / "asset-manifest.json").read_text(encoding="utf-8"))
        listed_assets = manifest["native_app"] + manifest["browser_theme"]
        missing = [path for path in listed_assets if not (ASSETS / path).is_file()]
        self.assertEqual(missing, [])

    def test_all_svg_assets_are_valid_xml(self) -> None:
        svg_files = list(ASSETS.rglob("*.svg"))
        self.assertGreaterEqual(len(svg_files), 6)
        for path in svg_files:
            with self.subTest(path=path.relative_to(ROOT)):
                root = ElementTree.parse(path).getroot()
                self.assertEqual(root.tag.rsplit("}", 1)[-1], "svg")

    def test_sound_assets_are_short_mono_pcm_wav_files(self) -> None:
        sound_files = sorted((ASSETS / "sounds").glob("*.wav"))
        self.assertEqual(
            [path.name for path in sound_files],
            ["error.wav", "ready.wav", "send.wav", "success.wav"],
        )
        for path in sound_files:
            with self.subTest(path=path.name), wave.open(str(path), "rb") as sound:
                self.assertEqual(sound.getnchannels(), 1)
                self.assertEqual(sound.getsampwidth(), 2)
                self.assertEqual(sound.getframerate(), 22050)
                self.assertLess(sound.getnframes() / sound.getframerate(), 1)

    def test_theme_asset_urls_resolve(self) -> None:
        stylesheet = ASSETS / "themes" / "jarvis-ui.css"
        css = stylesheet.read_text(encoding="utf-8")
        urls = re.findall(r'url\(["\']?([^)"\']+)', css)
        for url in urls:
            if "://" in url or url.startswith("data:"):
                continue
            with self.subTest(url=url):
                self.assertTrue((stylesheet.parent / url).resolve().is_file())

    def test_packaging_stages_the_complete_assets_directory(self) -> None:
        build_script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
        self.assertIn('xcopy /E /I /Y "assets" "%BUILD_ROOT%\\assets"', build_script)


if __name__ == "__main__":
    unittest.main()
