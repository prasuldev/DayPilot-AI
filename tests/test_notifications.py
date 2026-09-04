import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from productivity_agent.models import Priority
from productivity_agent.notifications import process_notifications
from productivity_agent.scheduler import build_plan
from productivity_agent.storage import Repository


class NotificationTests(unittest.TestCase):
    def test_claims_each_notification_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Repository(Path(directory) / "agent.db")
            repository.initialize()
            task = repository.add_task("Deep work", Priority.HIGH, 30)
            start = datetime(2030, 1, 1, 9)
            repository.replace_schedule(
                date(2030, 1, 1), start, datetime(2030, 1, 1, 17),
                build_plan([task], start, datetime(2030, 1, 1, 17)),
            )
            received = []

            count = process_notifications(
                repository, datetime(2030, 1, 1, 8, 55), 10,
                lambda title, message: received.append((title, message)),
            )
            repeated = process_notifications(
                repository, datetime(2030, 1, 1, 8, 56), 10,
                lambda title, message: received.append((title, message)),
            )

            self.assertEqual(count, 1)
            self.assertEqual(repeated, 0)
            self.assertEqual(received[0][0], "Upcoming task")


if __name__ == "__main__":
    unittest.main()
