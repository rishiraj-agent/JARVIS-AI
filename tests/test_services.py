from __future__ import annotations

import tempfile
import sqlite3
import unittest
from pathlib import Path

from jarvis.ai_client import AIError, LocalLanguageModel
from jarvis.notes_service import NotesService, ReminderService
from jarvis.storage import Storage
from jarvis.system_monitor import collect_system_snapshot
from jarvis.image_loader import ImageLoader
from jarvis.automation import run_command


class StorageAndServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "jarvis.sqlite3")
        self.notes = NotesService(self.storage)
        self.reminders = ReminderService(self.storage)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_notes_create_search_update_delete(self) -> None:
        note_id = self.notes.save("Project", "Remember the cyan theme")
        self.assertEqual(self.notes.search("cyan")[0]["id"], note_id)
        self.notes.save("Project updated", "Done", note_id)
        self.assertEqual(self.notes.search()[0]["title"], "Project updated")
        self.notes.delete(note_id)
        self.assertEqual(self.notes.search(), [])

    def test_reminder_validation_and_completion(self) -> None:
        with self.assertRaises(ValueError):
            self.reminders.create("", "2030-01-01 10:00")
        with self.assertRaises(ValueError):
            self.reminders.create("Review", "not-a-date")
        reminder_id = self.reminders.create("Review", "2030-01-01 10:00", "Check the outline")
        self.assertEqual(len(self.reminders.upcoming()), 1)
        self.assertEqual(self.reminders.upcoming()[0]["details"], "Check the outline")
        self.reminders.create("Review updated", "2030-01-02 10:00", "Updated", reminder_id)
        self.assertEqual(self.reminders.upcoming()[0]["title"], "Review updated")
        self.reminders.complete(reminder_id)
        self.assertEqual(self.reminders.upcoming(), [])

    def test_settings_and_search_history_persist(self) -> None:
        self.storage.save_settings({"model": "sample", "animations": True})
        self.storage.add_search("Windows desktop")
        self.assertEqual(self.storage.get_settings()["model"], "sample")
        self.assertEqual(self.storage.get_searches()[0], "Windows desktop")


class LocalLanguageModelTests(unittest.TestCase):
    def test_untrained_model_refuses_to_claim_generated_knowledge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            model = LocalLanguageModel(Path(directory) / "model.json", seed=7)
            self.assertFalse(model.is_trained)
            with self.assertRaisesRegex(AIError, "has not been trained"):
                model.generate("Hello", deterministic=True)

    def test_training_updates_parameters_and_checkpoint_reloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "model.json"
            model = LocalLanguageModel(checkpoint, seed=7)
            before = tuple(model.embedding[:16] + model.projection[:16])
            report = model.train_demo(epochs=1, learning_rate=0.01)
            after = tuple(model.embedding[:16] + model.projection[:16])
            self.assertGreater(report["training_steps"], 0)
            self.assertNotEqual(before, after)
            self.assertTrue(checkpoint.is_file())
            restored = LocalLanguageModel(checkpoint, seed=99)
            self.assertEqual(restored.training_steps, model.training_steps)
            self.assertEqual(
                restored.generate("J", deterministic=True),
                model.generate("J", deterministic=True),
            )
            self.assertIsInstance(model.training_loss, float)
            self.assertGreater(model.estimated_memory_bytes(), 0)

    def test_unicode_training_file_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "hindi.txt"
            source.write_text("Namaste, kaise ho?\nनमस्ते, कैसे हो?\nMain AI bana raha hoon.\n", encoding="utf-8")
            model = LocalLanguageModel(Path(directory) / "model.json", seed=4)
            result = model.train_file(source, epochs=1)
            self.assertTrue(result["dataset_sha256"])


class SystemMonitorTests(unittest.TestCase):
    def test_system_snapshot_has_real_platform_and_optional_metrics(self) -> None:
        snapshot = collect_system_snapshot()
        self.assertTrue(snapshot.operating_system)
        self.assertTrue(snapshot.processor)
        if snapshot.cpu_percent is not None:
            self.assertGreaterEqual(snapshot.cpu_percent, 0)
            self.assertLessEqual(snapshot.cpu_percent, 100)


class ReliabilityTests(unittest.TestCase):
    def test_missing_reference_image_is_optional(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.png"
            self.assertIsNone(ImageLoader().load(missing))

    def test_unknown_commands_are_not_executed(self) -> None:
        self.assertIsNone(run_command("run powershell.exe -Command whoami"))

    def test_app_imports_without_starting_gui(self) -> None:
        import main

        self.assertTrue(callable(main.main))
        self.assertTrue(hasattr(main, "JarvisApp"))

    def test_existing_reminder_database_migrates_details_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TABLE reminders (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
                    "due_at TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 0, "
                    "created_at TEXT NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO reminders(title, due_at, created_at) "
                    "VALUES('Existing', '2030-01-01 10:00', '2030-01-01')"
                )
                connection.commit()
            finally:
                connection.close()
            migrated = Storage(path)
            self.assertEqual(migrated.get_reminders()[0]["details"], "")

    def test_reference_image_is_part_of_project_assets(self) -> None:
        from config import REFERENCE_IMAGE_PATH

        self.assertTrue(REFERENCE_IMAGE_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
