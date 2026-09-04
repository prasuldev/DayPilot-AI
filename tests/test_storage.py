import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from productivity_agent.models import Priority, Recurrence, TaskStatus
from productivity_agent.storage import Repository


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.temporary_directory.name) / "agent.db")
        self.repository.initialize()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_add_and_update_task(self):
        goal = self.repository.add_goal("Prepare for interviews")
        task = self.repository.add_task(
            "Practice Python", Priority.HIGH, 60,
            datetime(2030, 1, 2, 12, 0), goal.id,
        )

        self.assertEqual(self.repository.get_task(task.id), task)
        self.assertEqual(self.repository.list_goals(), [goal])

        self.repository.set_task_status(task.id, TaskStatus.COMPLETED)
        self.assertIs(self.repository.get_task(task.id).status, TaskStatus.COMPLETED)

    def test_rejects_invalid_task(self):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.repository.add_task("Invalid", Priority.LOW, 0)

    def test_edit_reopen_delete_and_recurrence(self):
        task = self.repository.add_task("Daily review", Priority.MEDIUM, 20, recurrence=Recurrence.DAILY)
        updated = self.repository.update_task(
            task.id, title="Daily planning", priority=Priority.HIGH, estimated_minutes=25,
            deadline=None, goal_id=None, recurrence=Recurrence.DAILY,
        )
        self.assertEqual(updated.minutes_to_schedule, 25)
        self.repository.set_task_status(task.id, TaskStatus.COMPLETED)
        self.assertEqual(len(self.repository.list_tasks()), 2)
        self.repository.reopen_task(task.id, 10)
        self.assertEqual(self.repository.get_task(task.id).minutes_to_schedule, 10)
        self.repository.delete_task(task.id)
        self.assertIsNone(self.repository.get_task(task.id))

    def test_migrates_original_database(self):
        import sqlite3
        old_path = Path(self.temporary_directory.name) / "old.db"
        connection = sqlite3.connect(old_path)
        connection.execute("""CREATE TABLE tasks (
            id INTEGER PRIMARY KEY, title TEXT, priority TEXT, estimated_minutes INTEGER,
            deadline TEXT, status TEXT, goal_id INTEGER, created_at TEXT)""")
        connection.commit(); connection.close()
        migrated = Repository(old_path)
        migrated.initialize()
        task = migrated.add_task("After migration", Priority.LOW, 15)
        self.assertIs(task.recurrence, Recurrence.NONE)


if __name__ == "__main__":
    unittest.main()
